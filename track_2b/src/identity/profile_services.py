"""Private patient profile and a contact list that never grants authority."""
import re
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from records import services
from records.continuity import recipient
from records.metadata import validate_values
from .models import (BLOOD_GROUPS, CONTACT_RELATIONSHIPS, IDENTIFIER_TYPES,
                     CareCircleEntry, PatientPersonalDetails, Person)

PROFILE_LIMITS = {'full_name':160,'preferred_name':80,'email':254,'phone':40,'address':500,
                  'gender':60,'identifier_number':80,'identifier_issuer':80}
CONTACT_LIMITS = {'full_name':160,'email':254,'phone':40,'notes':500}


def text(value, maximum, required=False):
    if not isinstance(value,str) or len(value)>maximum or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',value):
        raise ValueError('Check the text fields and their lengths.')
    result=value.strip()
    if required and not result:
        raise ValueError('A name is required.')
    return result


def email(value):
    if value:
        try:
            validate_email(value)
        except ValidationError:
            raise ValueError('Enter a valid contact email address.') from None
    return value


def revision(value):
    if type(value) is not int or value<0:
        raise ValueError('Use the current nonnegative revision.')


def birth(person):
    return {'precision':person.birth_date_precision,'year':person.birth_year,
            'month':person.birth_month,'day':person.birth_day}


def profile_payload(workspace):
    item=PatientPersonalDetails.objects.filter(workspace=workspace).first()
    values={name:getattr(item,name) if item else '' for name in PROFILE_LIMITS}
    if item is None:
        values['full_name']=workspace.subject_patient.person.display_name
    values.update({'identifier_type':item.identifier_type if item else 'none',
        'blood_group':item.blood_group if item else 'unknown','birth_date':birth(workspace.subject_patient.person)})
    return {'revision':item.revision if item else 0,'values':values,
        'verification':'Patient-reported profile; identity and blood group are not verified.'}


def save_profile(user, workspace_id, values, expected_revision):
    revision(expected_revision)
    if not isinstance(values,dict) or set(values)!=set(PROFILE_LIMITS)|{'identifier_type','blood_group','birth_date'}:
        raise ValueError('Unexpected profile fields.')
    cleaned={name:text(values[name],limit,name=='full_name') for name,limit in PROFILE_LIMITS.items()}
    cleaned['email']=email(cleaned['email'])
    if values['identifier_type'] not in IDENTIFIER_TYPES or values['blood_group'] not in BLOOD_GROUPS:
        raise ValueError('Choose a supported ID type and blood group.')
    if values['identifier_type']=='none' and (cleaned['identifier_number'] or cleaned['identifier_issuer']):
        raise ValueError('Choose an ID type for the saved number.')
    if values['identifier_type']!='none' and not cleaned['identifier_number']:
        raise ValueError('Enter the ID number or select no ID saved.')
    validate_values({'document_type':'other','document_date':values['birth_date'],'facility_name':None})
    cleaned.update(identifier_type=values['identifier_type'],blood_group=values['blood_group'])
    with transaction.atomic():
        workspace,_=services.authorize(user,workspace_id,'manage_profile',lock=True)
        item=PatientPersonalDetails.objects.select_for_update().filter(workspace=workspace).first()
        if expected_revision!=(item.revision if item else 0):
            raise services.Conflict('Profile changed. Reload before saving.')
        person=Person.objects.select_for_update().get(pk=workspace.subject_patient.person_id)
        parts=values['birth_date']
        person.birth_date_precision=parts['precision']
        person.birth_year,person.birth_month,person.birth_day=parts['year'],parts['month'],parts['day']
        person.save(update_fields=['birth_date_precision','birth_year','birth_month','birth_day'])
        if item is None:
            item=PatientPersonalDetails.objects.create(workspace=workspace,updated_by=user,**cleaned)
        else:
            for key,value in cleaned.items():
                setattr(item,key,value)
            item.revision+=1; item.updated_by=user; item.updated_at=timezone.now()
            item.save(update_fields=[*cleaned,'revision','updated_by','updated_at'])
        services.audit(user,workspace,'profile.save',item)
        return item


def contact_payload(item):
    available=bool(item.recipient_user_id and item.recipient_user.is_active and item.recipient_user.person.status=='active')
    return {'id':item.pk,'revision':item.revision,'status':item.status,
        'values':{**{name:getattr(item,name) for name in CONTACT_LIMITS},'relationship':item.relationship,
                  'is_next_of_kin':item.is_next_of_kin,'is_emergency_contact':item.is_emergency_contact,
                  'recipient_id':item.recipient_user_id},
        'linked_account_name':item.recipient_user.person.display_name if item.recipient_user_id else None,
        'account_available':available,'access':'Saved contact only; no patient-record authority.'}


def save_contact(user,workspace_id,values,expected_revision,contact_id=None):
    revision(expected_revision)
    if not isinstance(values,dict) or set(values)!=set(CONTACT_LIMITS)|{'relationship','is_next_of_kin','is_emergency_contact','recipient_id'}:
        raise ValueError('Unexpected contact fields.')
    cleaned={name:text(values[name],limit,name=='full_name') for name,limit in CONTACT_LIMITS.items()}
    cleaned['email']=email(cleaned['email'])
    if values['relationship'] not in CONTACT_RELATIONSHIPS:
        raise ValueError('Choose a supported relationship.')
    for flag in ('is_next_of_kin','is_emergency_contact'):
        if type(values[flag]) is not bool:
            raise ValueError('Contact flags must be true or false.')
        cleaned[flag]=values[flag]
    cleaned['relationship']=values['relationship']
    with transaction.atomic():
        workspace,_=services.authorize(user,workspace_id,'manage_profile',lock=True)
        item=CareCircleEntry.objects.select_for_update().filter(pk=contact_id,workspace=workspace).first() if contact_id else None
        if contact_id and item is None:
            raise Http404
        if expected_revision!=(item.revision if item else 0):
            raise services.Conflict('Contact changed. Reload before saving.')
        requested=values['recipient_id']
        linked=None
        if requested is not None:
            linked=item.recipient_user if item and str(item.recipient_user_id)==str(requested) else recipient(requested,user)
        if linked and CareCircleEntry.objects.filter(workspace=workspace,recipient_user=linked,status='active').exclude(pk=item.pk if item else None).exists():
            raise services.Conflict('This account already has an active Care circle entry.')
        cleaned['recipient_user']=linked
        if item is None:
            if CareCircleEntry.objects.filter(workspace=workspace,status='active').count()>=100:
                raise services.Conflict('The 100-contact limit has been reached.')
            item=CareCircleEntry.objects.create(workspace=workspace,updated_by=user,**cleaned)
        else:
            if item.status!='active':
                raise services.Conflict('Restore this contact before editing.')
            for key,value in cleaned.items():
                setattr(item,key,value)
            item.revision+=1; item.updated_at=timezone.now(); item.updated_by=user
            item.save(update_fields=[*cleaned,'revision','updated_at','updated_by'])
        services.audit(user,workspace,'care_circle.save',item)
        return item


def contact_status(user,workspace_id,contact_id,status,expected_revision):
    revision(expected_revision)
    if status not in ('active','archived'):
        raise ValueError('Choose active or archived.')
    with transaction.atomic():
        workspace,_=services.authorize(user,workspace_id,'manage_profile',lock=True)
        item=CareCircleEntry.objects.select_for_update().filter(pk=contact_id,workspace=workspace).first()
        if not item:
            raise Http404
        if item.revision!=expected_revision:
            raise services.Conflict('Contact changed. Reload before saving.')
        if status=='active' and item.status!='active':
            if CareCircleEntry.objects.filter(workspace=workspace,status='active').count()>=100:
                raise services.Conflict('The 100-contact limit has been reached.')
            if item.recipient_user_id and CareCircleEntry.objects.filter(workspace=workspace,recipient_user_id=item.recipient_user_id,status='active').exists():
                raise services.Conflict('This linked account already has an active contact.')
        if item.status!=status:
            item.status=status; item.revision+=1; item.updated_at=timezone.now(); item.updated_by=user
            item.save(update_fields=['status','revision','updated_at','updated_by'])
            services.audit(user,workspace,'care_circle.'+status,item)
        return item
