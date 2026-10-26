"""
Editor integration regression through ue_cli exec --file, phases create/populate/open/check/cleanup.
Run Automation RunTests AgentTools.WBP.PrepareFixture after create and before populate.
Requires permission to create, edit, save and delete only /Game/__AgentToolsTests/IssuesFixture.
No project assets or gameplay data are modified. Pass --tab=<open output> to cleanup.
"""
import gc
import json
import unreal
import ue_input
import ue_wbp

PATH = '/Game/__AgentToolsTests/IssuesFixture'
LABEL = 'AgentToolsInput'


def run():
    phase = OPTS.get('phase', 'check')
    if phase == 'create':
        assert not unreal.EditorAssetLibrary.does_asset_exist(PATH), 'Fixture already exists; do not overwrite'
        factory = unreal.EditorUtilityWidgetBlueprintFactory()
        factory.set_editor_property('edit_after_new', False)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset('IssuesFixture', '/Game/__AgentToolsTests', unreal.EditorUtilityWidgetBlueprint, factory)
        assert bp is not None
        print('empty fixture created; run Automation RunTests AgentTools.WBP.PrepareFixture before --phase=populate')
    elif phase == 'populate':
        assert unreal.EditorAssetLibrary.does_asset_exist(PATH), 'Create the empty fixture first'
        assert len(ue_wbp.widgets(PATH)) == 1, 'Fixture must contain only its prepared root'
        ue_wbp.add_widget(PATH, 'root', 'ContentParent', 'Border', slot={'offset': (10, 10, 240, 40)})
        ue_wbp.add_widget(PATH, 'ContentParent', 'ContentText', 'TextBlock', var=False)
        content_slot = ue_wbp.widget(PATH, 'ContentText').slot
        try:
            ue_wbp.add_widget(PATH, 'ContentParent', 'RejectedText', 'TextBlock')
            raise AssertionError('Occupied ContentWidget silently replaced its child')
        except RuntimeError as error:
            assert 'already has a child' in str(error)
        assert ue_wbp.widget(PATH, 'ContentParent').get_content().get_name() == 'ContentText'
        assert ue_wbp.widget(PATH, 'ContentText').slot == content_slot
        ue_wbp.replace_widget(PATH, 'ContentText', 'TextBlock', new_name='ContentReplacement', var=False)
        ue_wbp.widget(PATH, 'ContentReplacement').set_text('ContentWidget regression passed')
        ue_wbp.add_widget(PATH, 'root', 'OrderPanel', 'VerticalBox', slot={'offset': (10, 70, 240, 220)})
        for name in ('A', 'B', 'C'):
            ue_wbp.add_widget(PATH, 'OrderPanel', name, 'TextBlock', slot={'padding': (1, 2, 3, 4)}, var=False)
            ue_wbp.widget(PATH, name).set_text(name)
        saved_slot = ue_wbp.widget(PATH, 'C').slot
        ue_wbp.add_widget(PATH, 'OrderPanel', 'D', 'TextBlock', before='B', var=False)
        panel = ue_wbp.widget(PATH, 'OrderPanel')
        names = lambda: [child.get_name() for child in panel.get_all_children()]
        assert names() == ['A', 'D', 'B', 'C']
        ue_wbp.insert_before(PATH, 'C', 'A')
        assert names() == ['C', 'A', 'D', 'B']
        assert ue_wbp.widget(PATH, 'C').slot == saved_slot
        ue_wbp.insert_after(PATH, 'D', 'B')
        assert names() == ['C', 'A', 'B', 'D']
        ue_wbp.replace_widget(PATH, 'B', 'TextBlock', new_name='BReplacement', var=False)
        assert names() == ['C', 'A', 'BReplacement', 'D']
        for name in ('C', 'A', 'BReplacement', 'D'):
            ue_wbp.widget(PATH, name).set_text(name)
        try:
            ue_wbp.add_widget(PATH, 'OrderPanel', 'WrongAnchor', 'TextBlock', before='ContentParent')
            raise AssertionError('Cross-parent anchor was accepted')
        except RuntimeError as error:
            assert 'same parent' in str(error)
        ue_wbp.add_widget(PATH, 'root', 'FixtureHeader', 'TextBlock', slot={'offset': (280, 10, 600, 40)}, var=False)
        ue_wbp.widget(PATH, 'FixtureHeader').set_text('AgentTools input fixture')
        ue_wbp.add_widget(PATH, 'root', 'FixtureScroll', 'ScrollBox', slot={'offset': (280, 70, 600, 300)})
        rows = unreal.new_object(unreal.VerticalBox, ue_wbp.widget_tree(PATH), 'Rows')
        ue_wbp.widget(PATH, 'FixtureScroll').add_child(rows)
        for index in range(24):
            name = 'Filler_%02d' % index
            ue_wbp.add_widget(PATH, 'Rows', name, 'TextBlock', slot={'padding': (0, 10, 0, 10)}, var=False)
            ue_wbp.widget(PATH, name).set_text('Filler row %02d' % index)
        ue_wbp.add_widget(PATH, 'Rows', 'InputRow', 'HorizontalBox')
        ue_wbp.add_widget(PATH, 'InputRow', 'FixtureLabel', 'TextBlock', slot={'size': (1, 'fill')}, var=False)
        ue_wbp.widget(PATH, 'FixtureLabel').set_text(LABEL)
        ue_wbp.add_widget(PATH, 'InputRow', 'FixtureInput', 'EditableTextBox', slot={'size': (1, 'fill')})
        ue_wbp.add_widget(PATH, 'InputRow', 'FixtureRun', 'Button', text='Run fixture')
        ue_wbp.add_widget(PATH, 'root', 'DragSource', 'Button', slot={'offset': (10, 310, 200, 40)}, text='Drag source')
        ue_wbp.add_widget(PATH, 'root', 'DropTarget', 'Border', slot={'offset': (10, 370, 200, 40)}, text='Drop target')
        ue_wbp.add_widget(PATH, 'root', 'LongText', 'MultiLineEditableText', slot={'offset': (10, 430, 320, 90)})
        ue_wbp.widget(PATH, 'LongText').set_text('MultilineFull_' + 'x' * 120 + '\nsecond line')
        ue_wbp.widget(PATH, 'LongText').set_hint_text('MultilineHint')
        ue_wbp.add_widget(PATH, 'root', 'RotatedClip', 'Border', slot={'offset': (700, 400, 160, 160)})
        border = ue_wbp.widget(PATH, 'RotatedClip')
        border.set_padding(unreal.Margin(0, 0, 0, 0))
        border.set_clipping(unreal.WidgetClipping.CLIP_TO_BOUNDS)
        border.set_render_transform_angle(45)
        ue_wbp.add_widget(PATH, 'RotatedClip', 'RotatedCanvas', 'CanvasPanel')
        ue_wbp.add_widget(PATH, 'RotatedCanvas', 'OutsideDiamond', 'TextBlock', slot={'offset': (-15, 60, 10, 30)}, var=False)
        ue_wbp.widget(PATH, 'OutsideDiamond').set_text('OutsideDiamond')
        ue_wbp.add_widget(PATH, 'RotatedCanvas', 'PartialDiamond', 'TextBlock', slot={'offset': (-5, 100, 20, 30)}, var=False)
        ue_wbp.widget(PATH, 'PartialDiamond').set_text('PartialDiamond')
        assert ue_wbp.save(PATH)
        print(json.dumps({'ok': True, 'content_widget': True, 'insert_order': names(), 'slot_preserved': True}))
    elif phase == 'open':
        bp = unreal.EditorAssetLibrary.load_asset(PATH)
        widget, tab_id = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem).spawn_and_register_tab_and_get_id(bp)
        assert widget is not None
        print('tab_id=%s' % tab_id)
    elif phase == 'check':
        assert ue_input.find_one('name=DragSource')
        assert ue_input.find_one('name=DropTarget')
        nodes = ue_input.find('text=' + LABEL, include_hidden=True)
        assert len(nodes) == 1
        print(json.dumps({'ok': True, 'target_visible': bool(ue_input.find_one('text=' + LABEL)), 'target': nodes[0]}, ensure_ascii=False))
    elif phase == 'verify-tools':
        assert not ue_input.find_one('name=OutsideDiamond'), 'Rotated AABB overlap was treated as visible'
        outside = ue_input.find('name=OutsideDiamond', include_hidden=True)
        assert outside and outside[0]['visible_rect'][2:] == [0, 0]
        partial = ue_input.find_one('name=PartialDiamond')
        assert partial and 'visible_point' in partial
        full = 'MultilineFull_' + 'x' * 120 + '\nsecond line'
        assert ue_input.read_text('name=LongText') == full
        assert ue_input.find_one('hint=MultilineHint')
        suggestions = ue_input.suggest('text=MultilineFull', root='name=LongText')
        assert suggestions['candidates']
        ue_input.click('name=PartialDiamond')
        print(json.dumps({'ok': True, 'rotated_outside_excluded': True, 'partial_point': partial['visible_point'], 'long_text_size': len(full), 'candidates': len(suggestions['candidates'])}))
    elif phase == 'cleanup':
        subsystem = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)
        tab_id = unreal.Name(OPTS['tab'])
        subsystem.close_tab_by_id(tab_id)
        subsystem.unregister_tab_by_id(tab_id)
        gc.collect()
        assert unreal.EditorAssetLibrary.delete_asset(PATH)
        assert not unreal.EditorAssetLibrary.does_asset_exist(PATH)
        print('fixture removed')
    else:
        raise RuntimeError('unknown fixture phase: ' + phase)


run()
gc.collect()
