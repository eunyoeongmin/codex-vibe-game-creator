"""Authenticated dashboard actions for project-owned creation tools."""
from message_catalog import text as _msg
import base64
from contextlib import nullcontext
import json
from pathlib import Path

import content_editor as content
import creator_tools as creator
from decisions import project_path
import production_tools as production
import gameplay_tools as gameplay
import studio_tools as studio
import live_tools as live


def route(handler, method, project_id, action, query, body):
    app = handler.app
    root = Path(app.state.project(project_id)['path'])
    if method == 'GET':
        if action == 'creator':
            with content.database(root) as db:
                result = {kind: content.entries(db, kind) for kind in ('content', 'story', 'checkpoint', 'variant', 'feedback', 'export', 'timeline', *gameplay.KINDS, *studio.KINDS)}
            result['live_points'] = live.points(root)
            result['play_save'] = [{**{k:v for k,v in r.items() if k not in ('snapshot','game_fingerprint')}, 'adapter':r['snapshot']['adapter'], 'version':r['snapshot']['version']} for r in result['play_save']]
            return result
        if action == 'creator-live-graph': return live.graph(root,query.get('point'))
        if action == 'creator-live-point': return live.point(root,query.get('id'))
        if action == 'creator-play-get':
            with content.database(root) as db: return content.get(db, 'play_save', query.get('id'))
        if action == 'creator-localization': return gameplay.localization_read(root, query.get('id'))
        if action == 'creator-sound': return studio.sound_resolve(root, query.get('id'), query.get('revision'))
        if action == 'creator-balance': return studio.balance_context(root, query.get('id'), query.get('revision'))
        if action == 'creator-graph': return production.graph(root)
        if action == 'creator-timeline-targets': return {'targets': production.timeline_targets(root, query.get('path'))}
        if action == 'creator-related': return production.related(root, query.get('id'))
        if action == 'creator-timeline': return production.timeline_resolve(root, query.get('id'), query.get('revision'))
        if action == 'content-show': return content.show(root, query.get('id'))
        if action == 'creator-history':
            if query.get('kind') not in ('story_history', 'content_edit', 'timeline_history', 'localization_edit', *(k + '_history' for k in (*gameplay.KINDS, *studio.KINDS))): raise ValueError(_msg('py.creator_api.invalid.history.kind'))
            with content.database(root) as db:
                return {'items': [r for r in content.entries(db, query['kind']) if r.get('id') == query.get('id') or r.get('dataset') == query.get('id')]}
        if action == 'creator-download':
            with content.database(root) as db: record = content.get(db, 'export', query.get('id'))
            path = project_path(root, record['path'])
            if creator.file_hash(path) != record['sha256']: raise ValueError(_msg('py.creator_api.export.archive.changed.export.again'))
            return path.read_bytes()
        if action == 'feedback-image':
            with content.database(root) as db: record = content.get(db, 'feedback', query.get('id'))
            return {'image': 'data:image/png;base64,' + base64.b64encode(project_path(root, record['image']).read_bytes()).decode('ascii')}
        raise ValueError(_msg('py.creator_api.unknown.creation.tool.request'))
    with app.lock:
        session = app.sessions.get(project_id)
        with session.lock if session else nullcontext():
            if session and session.turn_id and action not in ('feedback-save', 'variant-preview'):
                raise ValueError(_msg('ui.wait.for.the.current.task.to.finish'))
            if action == 'creator-live-capture': return live.capture(root,body)
            if action == 'creator-live-branch': return live.branch(root,body.get('id'))
            if action == 'creator-live-select': return live.select(root,body.get('id'),body.get('choice'),body.get('alternative_fingerprint'))
            if action == 'creator-live-preview':
                saved,variant=live.variant_context(root,body.get('id'))
                files=creator.game_files(project_path(root,variant['folder']),include_media=True)
                return {'main':app.preview(project_id,saved['entry']), 'alternative':app.preview(project_id,saved['entry'],variant=variant), 'snapshot':saved['snapshot'],
                        'alternative_fingerprint':live.build_fingerprint({name:creator.file_hash(path) for name,path in files.items()})}
            if action == 'content-register': return content.register(root, body.get('definition'), body.get('revision'))
            if action == 'creator-sound-save': return studio.sound_save(root, body.get('values'), body.get('revision'))
            if action == 'creator-sound-publish': return studio.sound_publish(root, body.get('id'), body.get('revision'))
            if action == 'creator-balance-run': return studio.balance_result(root, body)
            if action == 'creator-play-save': return gameplay.play_save(root, body)
            if action == 'creator-localization-save': return gameplay.localization_edit(root, body)
            if action == 'creator-design-save': return gameplay.design_save(root, body.get('kind'), body.get('values'), body.get('revision'))
            if action == 'creator-experiment-build': return gameplay.experiment_build(root, body.get('id'), body.get('revision'))
            if action == 'creator-design-approve': return gameplay.approve(root, body.get('kind'), body.get('id'), body.get('revision'), body.get('user_quote'), body.get('chosen'))
            if action == 'content-save':
                return content.save_row(root, body.get('id'), body.get('row_id'), body.get('values'), body.get('digest'), body.get('revision'))
            if action == 'story-save': return creator.story_save(root, body.get('values'), body.get('revision'))
            if action == 'creator-timeline-save': return production.timeline_save(root, body.get('values'), body.get('revision'))
            if action == 'creator-timeline-publish': return production.timeline_publish(root, body.get('id'), body.get('revision'))
            if action == 'creator-relation-save': return production.relation_save(root, body.get('values'))
            if action == 'feedback-save': return creator.feedback_save(root, body)
            if action == 'checkpoint-add':
                with app.state.lock: return creator.checkpoint(root, body.get('name'))
            if action == 'checkpoint-restore':
                if body.get('confirmation') != 'restore:' + str(body.get('id')): raise ValueError(_msg('py.creator_api.select.a.checkpoint.and.confirm.restoration'))
                with app.state.lock:
                    result = creator.restore(root, body.get('id'))
                    for question in app.state.questions(project_id): app.state.answer_question(project_id, question['id'])
                    if session: session.live_questions.clear()
                    app.state.merge_info(project_id, last_context=None, last_request=None, planning={})
                return result
            if action == 'variant-add': return creator.variant_create(root, body.get('name'), body.get('hypothesis'), body.get('entry'))
            if action == 'variant-adopt':
                if body.get('confirmation') != 'adopt:' + str(body.get('id')): raise ValueError(_msg('py.creator_api.select.an.alternative.and.confirm.adoption'))
                with app.state.lock: return creator.variant_adopt(root, body.get('id'))
            if action == 'variant-preview':
                with content.database(root) as db: record = content.get(db, 'variant', body.get('id'))
                return {'main': app.preview(project_id, record['entry']),
                        'alternative': app.preview(project_id, record['entry'], variant=record)}
            if action == 'game-export': return creator.export_game(root, body.get('entry'), body.get('name'))
            if action == 'creator-request':
                session = app.session(project_id)
                request = content.text(body.get('text'), 'request', 10000)
                kind = body.get('kind')
                attachments = []
                workspace_root = None
                if kind == 'live_setup':
                    context={'guide':'guide/play-workspace.md','registry':live.registry(root)}
                elif kind == 'live_point':
                    context=live.context(root,body.get('id'))
                    if context['changed_since_capture']: live.fail('game_changed')
                elif kind == 'live_variant':
                    saved,variant=live.variant_context(root,body.get('id'))
                    context=live.context(root,saved['id'])
                    workspace_root=project_path(root,variant['folder'])
                    context.update(variant_id=variant['id'],folder=str(workspace_root),project_relative_folder=variant['folder'],guide=str(root/'guide/play-workspace.md'))
                elif kind == 'live_system':
                    registry=live.graph(root)
                    if registry.get('revision') != body.get('revision'): live.fail('registry_changed')
                    selected=next((n for n in registry['nodes']+registry['edges'] if n['id']==body.get('id')),None)
                    if selected is None: live.fail('invalid_id')
                    ids={selected['id']} if 'source' not in selected else {selected['source'],selected['target']}
                    edges=[e for e in registry['edges'] if e['source'] in ids or e['target'] in ids]
                    ids|={e[k] for e in edges for k in ('source','target')}
                    context={'guide':'guide/play-workspace.md','selected':selected,'nodes':[n for n in registry['nodes'] if n['id'] in ids],'edges':edges}
                    refs={ref for item in context['nodes']+edges for ref in item['refs']}
                    context['records']=[n for n in production.graph(root)['nodes'] if n['id'] in refs]
                elif kind in ('sound_setup','balance_setup'):
                    context = {'guide': 'guide/sound-balance.md'}
                elif kind in ('soundscape','sound_integration'):
                    context = studio.sound_resolve(root,body.get('id'),body.get('revision'))
                elif kind == 'balance':
                    context = studio.balance_context(root,body.get('id'),body.get('revision'))
                elif kind == 'balance_run':
                    context = gameplay.get_record(root,'balance_run',body.get('id'),body.get('revision'))
                    definition = studio.balance_context(root,context['balance_id'],context['balance_revision'])
                    if definition['fingerprint'] != context['fingerprint']: raise ValueError(_msg('py.creator_api.game.changed.since.this.comparison.run.it.again'))
                    context = {**context, 'definition': definition['record']}
                elif kind in ('play_setup', 'localization_setup', 'experiment_setup', 'integration_setup', 'content_plan_setup'):
                    context = {'guide': 'guide/gameplay-tools.md', 'relationships': production.graph(root) if kind == 'integration_setup' else None}
                elif kind in ('experiment', 'integration', 'content_plan', 'localization'):
                    context = gameplay.get_record(root, kind, body.get('id'), body.get('revision'))
                    if kind == 'localization': context = gameplay.localization_read(root, body.get('id'))
                    if kind == 'integration':
                        context = {**context, 'current_evidence': production.graph(root)}
                        context['evidence_changed'] = context['fingerprint'] != context['current_evidence']['fingerprint']
                elif kind == 'relationship':
                    context = production.related(root, body.get('id'))
                    if context['fingerprint'] != body.get('fingerprint'): raise ValueError(_msg('py.creator_api.relationships.changed.reload.before.sending'))
                elif kind in ('timeline', 'timeline_integration'):
                    context = production.timeline_resolve(root, body.get('id'), body.get('revision'))
                    context['runtime_path'] = 'game-tools/timeline-player.js'
                    context['json_path'] = 'content/timelines/' + context['id'] + '.json'
                elif kind == 'content_setup':
                    with content.database(root) as db: context = {'registered': content.entries(db, 'content')}
                elif kind == 'content':
                    info = content.show(root, body.get('id'))
                    if info['digest'] != body.get('digest') or info['definition']['revision'] != body.get('revision'):
                        raise ValueError(_msg('py.creator_api.content.changed.reload.before.sending'))
                    row = next((r for r in info['rows'] if r.get(info['definition']['id_field']) == body.get('row_id')), None)
                    if row is None: raise ValueError(_msg('py.creator_api.unknown.content.row'))
                    context = {'definition': info['definition'], 'row': row, 'digest': info['digest']}
                elif kind in ('story', 'feedback', 'variant'):
                    if kind == 'story' and not body.get('id'): context = {'new_story': True}
                    else:
                        with content.database(root) as db: context = content.get(db, kind, body.get('id'))
                        if kind == 'story' and context['revision'] != body.get('revision'): raise ValueError(_msg('py.creator_api.story.record.changed.reload.before.sending'))
                    if kind == 'feedback' and context.get('image'): attachments.append(project_path(root, context['image']))
                    if kind == 'variant':
                        if context['status'] != 'comparison': raise ValueError(_msg('py.creator_api.this.alternative.was.already.selected'))
                        context = {k: v for k, v in context.items() if k != 'baseline'}
                        workspace_root = project_path(root, context['folder'])
                        context['project_relative_folder'] = context['folder']
                        context['folder'] = str(workspace_root)
                else: raise ValueError(_msg('py.creator_api.unknown.request.kind'))
                prompt = session.instructions.render('creator_request', kind=kind, request=request, context=json.dumps(context, ensure_ascii=False))
                session.send_message(prompt, attachments=attachments, instruction_section='creator_request', display_text=request, workspace_root=workspace_root)
                app.state.merge_info(project_id, last_request=request)
                return {'accepted': True}
    raise ValueError(_msg('py.creator_api.unknown.creation.tool.request'))
