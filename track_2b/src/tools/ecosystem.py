"""Entry point for explicitly isolated synthetic integration evaluation."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ecosystem import prepare,environment,run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','plan','init','start','seed','verify','workflows','journeys','process','evaluate','report'])
    parser.add_argument('--profile',choices=['smoke','functional','stress'],default='smoke')
    parser.add_argument('--max-documents',type=int,default=32)
    parser.add_argument('--max-jobs',type=int,default=16)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--case-ids',nargs='+')
    options=parser.parse_args()
    if not 1<=options.max_documents<=64 or not 1<=options.max_jobs<=32: parser.error('Use bounded batches')
    if options.operation=='prepare':
        with environment.operation_lock():suite=prepare.prepare()
        result={'version':suite['version'],'patients':len(suite['patients']),'documents':len(suite['documents'])}
    elif options.operation=='plan': result=run.dry_run(options.profile)
    elif options.operation=='init': environment.initialize();result={'initialized':True,'project':environment.PROJECT}
    elif options.operation=='start':
        environment.initialize();environment.compose('up','--build','--detach','--wait','app');result={'app':environment.APP}
    elif options.operation=='seed': result=run.seed(options.profile,options.max_documents)
    elif options.operation=='verify': result=run.verify(options.profile)
    else:
        from ecosystem import evaluate
        extra={'case_ids':options.case_ids} if options.operation=='evaluate' else {}
        result=getattr(evaluate,options.operation)(profile=options.profile,live=options.live,max_jobs=options.max_jobs,**extra)
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':
    try: main()
    except Exception as error:
        # Never print provider/form/parser exceptions containing source text or keys.
        print(json.dumps({'failed':True,'error_type':type(error).__name__,
            'message':str(error) if type(error) is ValueError else 'Operation failed; inspect bounded receipts and service health.'}),file=sys.stderr)
        raise SystemExit(1)
