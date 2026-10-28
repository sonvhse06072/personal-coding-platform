#!/usr/bin/env python3
"""Optional isolated browser fixture proof. No services, credentials or live DB.

Requires Playwright in a development environment and an explicit browser binary.
Never downloads a browser or contacts PCP Local. Screenshots are labeled fixtures.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'services/runtime'),str(ROOT/'services/runtime/tests')]
from app.dashboard_local import build_local_snapshot
from app.dashboard_ui_local import LOCAL_DASHBOARD_HTML
from test_dashboard_local import ReadStore, NOW, held_row
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    snapshot=build_local_snapshot(ReadStore(),clock=NOW)
    snapshot.update(instance='FIXTURE · retained held-job shape',source='0c968dd99199c73f3fbc89c0b59da168844e8f73')
    state={'snapshot':snapshot,'authenticated':False,'offline':False};requests=[];errors=[]
    html=LOCAL_DASHBOARD_HTML.replace('<main class="wrap">','<main class="wrap"><p class="pill">FIXTURE PREVIEW · synthetic observations · not connected to V3</p>')
    def route(r):
        path=r.request.url.split('fixture.pcp.invalid',1)[1];requests.append((r.request.method,path))
        if path=='/dashboard':return r.fulfill(content_type='text/html',body=html)
        if path=='/v1/dashboard/session':
            assert r.request.method=='POST';state['authenticated']=True;return r.fulfill(json={'status':'ok'})
        if path=='/v1/dashboard/snapshot':
            if state['offline']:return r.abort()
            if not state['authenticated']:return r.fulfill(status=401,json={'detail':'Authentication required'})
            return r.fulfill(json=state['snapshot'])
        raise AssertionError('Unexpected fixture request: '+path)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.browser,headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1100});page.route('https://fixture.pcp.invalid/**',route)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('https://fixture.pcp.invalid/dashboard');page.get_by_label('Dashboard read token').wait_for(state='visible')
        page.get_by_label('Dashboard read token').fill('synthetic-read-token');page.get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_role('heading',name='Job 51a11aa704362d84ae5c7b70e85741f1').wait_for()
        assert page.get_by_text('gpt-6-luna',exact=False).count()>=1
        assert page.get_by_text('213',exact=True).count()>=1
        assert not page.get_by_role('button',name='Run',exact=True).count()
        assert not page.locator('[role="progressbar"]').count()
        for width,height,name in [(1440,1100,'held-desktop'),(390,844,'held-mobile')]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(args.output/(name+'.png')),full_page=True)
        for name in ('empty','waiting_auth','unavailable','stale'):
            v=deepcopy(snapshot)
            if name=='stale':v['jobs'][0]['activity']='stale';v['jobs'][0]['activity_age_seconds']=540
            else:v['jobs']=[];v['state']=name
            if name=='waiting_auth':v['readiness']={'state':'waiting_auth'}
            if name=='unavailable':v['observation']='unavailable'
            state['snapshot']=v;page.evaluate('refresh()');page.wait_for_timeout(80)
            assert page.locator('#jobs').inner_text()
        for status in ('completed','failed','cancelled','executing'):
            row=held_row();row.update(status=status,error=None,updated_at=NOW-timedelta(hours=1))
            row['checkpoint']['pcp_local_execution'].update(started_at=(NOW-timedelta(hours=2)).isoformat(),duration_seconds=45)
            state['snapshot']=build_local_snapshot(ReadStore([row]),clock=NOW)
            page.evaluate('refresh()');page.wait_for_timeout(80)
            job=state['snapshot']['jobs'][0]
            assert job['activity']==('stale' if status=='executing' else status)
            if status!='executing':assert job['elapsed_seconds']==45
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        for stage in ('verified_uncommitted','commit_uncertain','verified'):
            row=held_row();row['checkpoint']['pcp_local_execution']['state']=stage
            state['snapshot']=build_local_snapshot(ReadStore([row]),clock=NOW)
            page.evaluate('refresh()');page.wait_for_timeout(80)
            assert stage.replace('_',' ') in page.locator('#jobs').inner_text()
        state['offline']=True;page.evaluate('refresh()');page.wait_for_timeout(80)
        assert 'Offline' in page.locator('#connection').inner_text()
        assert not errors,errors
        browser.close()
    evidence={'kind':'fixture_browser_proof','live_rollout':False,'states':['waiting_dashboard_auth','held','empty','waiting_auth','unavailable','stale','completed','failed','cancelled','verified_uncommitted','commit_uncertain','verified','offline'],
              'viewports':[1440,390],'overflow':False,'page_errors':errors,'requests':requests}
    (args.output/'browser-proof.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k!='requests'}))


if __name__=='__main__':main()
