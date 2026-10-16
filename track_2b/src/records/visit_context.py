"""Explicit, private patient-context snapshots for a visit preparation draft.

The caller owns the approved document packet, transaction and workspace lock.
This module never expands a packet's sharing scope or writes domain records.
"""
from copy import deepcopy
import re
import uuid

from django.db.models import F, IntegerField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils import timezone

from identity.models import PatientPersonalDetails
from . import services
from .metadata import UNKNOWN_DATE
from .models import (CareHistory, CareTeamAssignment, JournalEvent, JournalHistory,
                     MedicationEntry, PatientHealthConcern, ReportedPractitioner)


VERSION = 'visit-context-v1'
FLAGS = ('profile', 'medications', 'journal', 'care')
LIMITS = {'medication': 20, 'journal': 12, 'concern': 8, 'care': 8}
USE_STATUS = {
    'reported_taken': 'Patient reported taking; current use is not established',
    'reported_prescribed': 'Patient reported prescribed; actual use is not established',
    'not_taken': 'Patient reported not taking',
    'unknown': 'Use unknown',
}


def validate_options(parameters):
    """Accept only explicit bounded patient instructions and inclusion switches."""
    allowed = {'packet_id', 'visit_brief', 'visit_focus', 'patient_goals',
               'patient_questions', 'include_context'}
    if not isinstance(parameters, dict) or set(parameters) - allowed:
        raise ValueError('Unexpected visit overview options.')
    if parameters.get('visit_brief') is not True:
        raise ValueError('Choose the visit preparation overview explicitly.')
    try:
        packet_id = str(uuid.UUID(parameters['packet_id']))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('Select a saved visit collection.') from None
    flags = parameters.get('include_context', {key: False for key in FLAGS})
    if not isinstance(flags, dict) or set(flags) != set(FLAGS) or any(type(value) is not bool for value in flags.values()):
        raise ValueError('Choose each private context option explicitly.')
    normalized = {'packet_id': packet_id, 'visit_brief': True, 'include_context': flags.copy()}
    for key in ('visit_focus', 'patient_goals', 'patient_questions'):
        value = parameters.get(key, '')
        if not isinstance(value, str) or len(value) > 600 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', value):
            raise ValueError('Keep each visit instruction within 600 characters and remove control characters.')
        normalized[key] = value.strip()
    return normalized


def authorize_context(user, workspace_id, flags, lock=False):
    if not isinstance(flags, dict) or set(flags) != set(FLAGS) or any(type(value) is not bool for value in flags.values()):
        raise ValueError('Invalid private context scope.')
    workspace, _ = services.authorize(user, workspace_id, lock=lock)
    if any(flags.values()):
        services.authorize(user, workspace_id, 'manage_profile', lock=lock)
    if flags['medications']:
        services.authorize(user, workspace_id, 'manage_medications', lock=lock)
    return workspace


def _date_text(parts):
    precision = parts['precision']
    if precision == 'unknown':
        return 'Unknown'
    value = f"{parts['year']:04d}"
    if precision in ('month', 'day'):
        value += f"-{parts['month']:02d}"
    if precision == 'day':
        value += f"-{parts['day']:02d}"
    return value


def _dated(query, field):
    """Newest reported partial-date components; never upload/creation order."""
    return query.annotate(**{
        '_reported_' + component: Cast(KeyTextTransform(component, field), IntegerField())
        for component in ('year', 'month', 'day')
    }).order_by(*(F('_reported_' + component).desc(nulls_last=True)
                  for component in ('year', 'month', 'day')), 'id')


def _history(item, kind, coverage):
    if kind == 'journal':
        row = JournalHistory.objects.filter(workspace_id=item.workspace_id, event_id=item.pk,
                                           revision=item.revision).first()
    else:
        row = CareHistory.objects.filter(workspace_id=item.workspace_id, target_kind=kind,
                                         target_id=item.pk, revision=item.revision).first()
    if row is not None:
        return deepcopy(row.snapshot)
    # SQLite development fixtures do not install PostgreSQL history triggers.
    # Freeze the locked current row and disclose that history was unavailable.
    coverage['missing_immutable_history'] += 1
    return None


def _entry(entries, item, kind, area, label, text, parts, meaning, href):
    if not text.strip() or len(text) > 2600:
        raise ValueError('Private context cannot be captured without losing source detail.')
    entries.append({'id': f'p{len(entries) + 1}', 'kind': kind, 'area': area,
                    'label': label, 'text': text, 'date': deepcopy(parts),
                    'date_meaning': meaning, 'provenance': 'patient_reported',
                    'href': href, 'revision': item.revision, 'target_id': str(item.pk),
                    'updated_at': item.updated_at.isoformat()})


def _bounded(query, kind, coverage):
    count = query.count()
    rows = list(query[:LIMITS[kind]])
    coverage['available_counts'][kind] = count
    coverage['omitted_counts'][kind] = max(0, count - len(rows))
    return rows


def snapshot(user, workspace, options, packet):
    """Capture requested context only, under the caller's atomic workspace lock."""
    flags = options['include_context']
    authorize_context(user, workspace.pk, flags, lock=True)
    if packet.workspace_id != workspace.pk or str(packet.pk) != options['packet_id']:
        raise ValueError('Visit context belongs to another collection.')
    root = f'/app/workspaces/{workspace.pk}'
    entries = []
    coverage = {'counts': {kind: 0 for kind in ('profile', *LIMITS)},
                'available_counts': {}, 'omitted_counts': {},
                'limits': LIMITS.copy(), 'missing_immutable_history': 0,
                'structured_measurements_available': False,
                'appointment_lifecycle_available': False}
    if flags['profile']:
        item = PatientPersonalDetails.objects.select_for_update().filter(workspace=workspace).first()
        facts = []
        if item:
            if item.blood_group != 'unknown':
                facts.append(f'Blood group (patient reported, unverified): {item.blood_group}')
            if item.gender.strip():
                facts.append(f'Gender (patient reported): {item.gender}')
            if facts:
                _entry(entries, item, 'profile', 'basics', 'Patient-reported basics', '\n'.join(facts),
                       UNKNOWN_DATE, 'Profile value; no clinical measurement date recorded', root + '/account')
        coverage['available_counts']['profile'] = int(bool(facts))
        coverage['omitted_counts']['profile'] = 0
    if flags['medications']:
        query = MedicationEntry.objects.select_for_update().filter(workspace=workspace, status='active').order_by(
            F('value_year').desc(nulls_last=True), F('value_month').desc(nulls_last=True),
            F('value_day').desc(nulls_last=True), 'id')
        for item in _bounded(query, 'medication', coverage):
            parts = {'precision': item.date_precision, 'year': item.value_year,
                     'month': item.value_month, 'day': item.value_day}
            facts = [f'Medicine: {item.medicine_name}', f'Reported status: {USE_STATUS[item.use_status]}',
                     f'Reported visit date: {_date_text(parts)}']
            for label, value in (('Dose as recorded', item.dose), ('Frequency as recorded', item.frequency),
                                 ('Route as recorded', item.route), ('Instructions/notes as recorded', item.instructions)):
                if value:
                    facts.append(f'{label}: {value}')
            _entry(entries, item, 'medication', 'medications', item.medicine_name, '\n'.join(facts), parts,
                   'Patient-reported medication visit date; not a start or stop date',
                   f'/workspaces/{workspace.pk}/medications/')
            entries[-1]['medication'] = {'name': item.medicine_name, 'dose': item.dose,
                                         'frequency': item.frequency, 'use_status': item.use_status}
    if flags['journal']:
        query = _dated(JournalEvent.objects.select_for_update().filter(workspace=workspace, status='active'), 'occurrence')
        for item in _bounded(query, 'journal', coverage):
            historical = _history(item, 'journal', coverage)
            value = historical if historical is not None else {
                'category': item.category, 'description': item.description, 'occurrence': item.occurrence,
                'severity': item.severity, 'occurrence_time': item.occurrence_time,
                'timezone_name': item.timezone_name}
            facts = [f"Patient-reported {value['category']}: {value['description']}"]
            if value['severity'] is not None:
                facts.append(f"Reported severity: {value['severity']}/10")
            if value.get('occurrence_time'):
                facts.append(f"Reported local time: {value['occurrence_time']} ({value['timezone_name']})")
            _entry(entries, item, 'journal', 'symptoms' if value['category'] == 'symptom' else 'history',
                   'Journal observation', '\n'.join(facts), value['occurrence'],
                   'Patient-reported occurrence; partial and unknown dates retained', root + f'/journal/{item.pk}')
    if flags['care']:
        query = _dated(PatientHealthConcern.objects.select_for_update().filter(workspace=workspace, status='active'), 'onset')
        for item in _bounded(query, 'concern', coverage):
            historical = _history(item, 'concern', coverage)
            value = historical if historical is not None else {
                'title': item.title, 'description': item.description, 'certainty': item.certainty,
                'kind': item.kind, 'onset': item.onset}
            certainty = ('Patient-reported diagnosis; not clinically verified'
                         if value['certainty'] == 'patient_reported_diagnosis' else 'Unconfirmed patient concern')
            facts = [f"Concern: {value['title']}", f"Type: {value['kind']}", f'Certainty: {certainty}']
            if value['description']:
                facts.append(f"Description: {value['description']}")
            _entry(entries, item, 'concern', 'history', value['title'], '\n'.join(facts), value['onset'],
                   'Patient-reported concern onset', root + '/care/concerns')
        query = _dated(CareTeamAssignment.objects.select_for_update(of=('self',)).filter(
            workspace=workspace, status='active', practitioner__workspace=workspace,
            practitioner__status='active'), 'start_date')
        assignments = _bounded(query, 'care', coverage)
        practitioners = {item.pk: item for item in ReportedPractitioner.objects.select_for_update().filter(
            workspace=workspace, pk__in=[item.practitioner_id for item in assignments], status='active').order_by('id')}
        for item in assignments:
            historical = _history(item, 'assignment', coverage)
            value = historical if historical is not None else {
                'role': item.role, 'participation': item.participation, 'start_date': item.start_date,
                'end_date': item.end_date, 'notes': item.notes}
            practitioner = practitioners.get(item.practitioner_id)
            if practitioner is None:
                raise services.Conflict('A selected care relationship changed.')
            practitioner_history = _history(practitioner, 'practitioner', coverage)
            doctor = practitioner_history if practitioner_history is not None else {
                'name': practitioner.name, 'specialty': practitioner.specialty, 'facility': practitioner.facility}
            facts = [f"Reported practitioner: {doctor['name']}", f"Care role: {value['role']}",
                     f"Patient-reported participation: {value['participation']}",
                     f"Relationship end date: {_date_text(value['end_date'])}",
                     'Reported relationship; professional identity unverified; no access granted by this relationship.']
            for label, content in (('Specialty', doctor['specialty']), ('Facility', doctor['facility']),
                                   ('Relationship notes', value['notes'])):
                if content:
                    facts.append(f'{label}: {content}')
            _entry(entries, item, 'care', 'coordination', 'Care relationship', '\n'.join(facts), value['start_date'],
                   'Patient-reported care relationship start; not an appointment date', root + '/care/team')
    for entry in entries:
        coverage['counts'][entry['kind']] += 1
    return {'version': VERSION, 'as_of': timezone.localdate().isoformat(),
            'visit': {'purpose': packet.purpose, 'focus': options['visit_focus'],
                      'goals': options['patient_goals'], 'questions': options['patient_questions']},
            'included': flags.copy(), 'entries': entries, 'coverage': coverage}


def changed_since_request(task):
    """Status/revision checks only; never silently refresh saved inference data."""
    saved = task.parameters.get('visit_context')
    if not saved:
        return False
    models = {'profile': PatientPersonalDetails, 'medication': MedicationEntry,
              'journal': JournalEvent, 'concern': PatientHealthConcern, 'care': CareTeamAssignment}
    for entry in saved['entries']:
        query = models[entry['kind']].objects.filter(workspace_id=task.workspace_id,
            pk=entry['target_id'], revision=entry['revision'])
        if entry['kind'] != 'profile': query = query.filter(status='active')
        if not query.exists(): return True
    # Also disclose newly saved context. It will require a new explicit request.
    for kind, flag in [('profile', 'profile'), ('medication', 'medications'),
                       ('journal', 'journal'), ('concern', 'care'), ('care', 'care')]:
        if saved['included'][flag] and models[kind].objects.filter(
                workspace_id=task.workspace_id, updated_at__gt=task.created_at).exists():
            return True
    if saved['included']['care'] and ReportedPractitioner.objects.filter(
            workspace_id=task.workspace_id, updated_at__gt=task.created_at).exists():
        return True
    return False
