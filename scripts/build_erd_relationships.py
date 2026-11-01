"""Build review-only ERD relationship views as editable draw.io and SVG files.

Run from any directory with Python 3. No Django or database connection is used.
The diagrams focus on keys/relationships; the supplied PNG retains full attributes.
"""
from pathlib import Path
import html
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'architecture' / 'erd-relations'
COLORS = {'account': '#dcecff', 'reference': '#def2df', 'comparison': '#fff0cf'}
NODES = {
 'ACCOUNT': ('account', ['PK account_id : UUID', 'UK login_email : email', 'password -> password_hash', 'is_active : boolean', 'Django auth fields (see mapping)']),
 'STUDENT': ('account', ['PK student_id : UUID', 'UK/FK account_id -> ACCOUNT', 'Each student has one account']),
 'ROLE': ('account', ['PK role_id : UUID', 'UK role_name : allowed role']),
 'ACCOUNT_ROLE': ('account', ['PK assignment_id : UUID [implemented]', 'UK (account_id, role_id)', 'FK account_id -> ACCOUNT [recipient]', 'FK role_id -> ROLE', 'FK assigned_by -> ACCOUNT [nullable]']),
 'SKILL': ('account', ['PK skill_id : UUID', 'UK skill_name', 'status : active / retired']),
 'STUDENT_SKILL': ('account', ['KEY (student_id, skill_id)', 'FK student_id -> STUDENT', 'FK skill_id -> SKILL', 'proficiency_level : agreed scale']),
 'STUDENT_COURSE': ('account', ['KEY (student_id, course_item_id)', 'FK student_id -> STUDENT', 'FK (course_item_id, course_kind)', ' -> CONTENT_ITEM(item_id, kind)', "CHECK course_kind = 'course'"]),
 'CONTENT_ITEM': ('reference', ['PK item_id : UUID', 'kind : career/job/course/resource/insight', 'UK (item_id, kind)', 'retired_at : nullable']),
 'CONTENT_VERSION': ('reference', ['PK version_id : UUID', 'FK (item_id, kind) -> CONTENT_ITEM', 'UK (item_id, version_no)', 'UK (version_id, kind)', 'FK created_by -> ACCOUNT', 'FK published_by -> ACCOUNT [nullable]', 'REMOVE UK (item_id, kind) here']),
 'CONTENT_REVIEW': ('reference', ['PK review_id : UUID', 'FK version_id -> CONTENT_VERSION', 'FK reviewer_id -> ACCOUNT', 'reviewed_revision = draft revision', 'approval checked at publication']),
 'REFERENCE_SOURCE': ('reference', ['PK source_id : UUID', 'source title / URL / collection date']),
 'CONTENT_SOURCE': ('reference', ['KEY (version_id, source_id)', 'FK version_id -> CONTENT_VERSION', 'FK source_id -> REFERENCE_SOURCE']),
 'CONTENT_REQUIREMENT': ('reference', ['KEY (version_id, skill_id)', 'FK (version_id, kind) -> CONTENT_VERSION', 'FK skill_id -> SKILL', "CHECK kind IN ('career', 'job')", 'required_level / mandatory / weight']),
 'CONTENT_SKILL': ('reference', ['KEY (version_id, skill_id)', 'FK (version_id, kind) -> CONTENT_VERSION', 'FK skill_id -> SKILL', "CHECK kind IN ('course', 'resource')", 'coverage_level : agreed scale']),
 'CONTENT_DETAILS': ('reference', ['PK/FK version_id : one row per version', 'FK (version_id, kind) -> CONTENT_VERSION', 'FK company_id -> COMPANY [nullable]', 'kind matches the actual content kind', 'Type-specific fields validated']),
 'COMPANY': ('reference', ['PK company_id : UUID', 'Reference organization only']),
 'MATCH_RESULT': ('comparison', ['PK match_id : UUID', 'FK student_id -> STUDENT', 'FK (target_version_id, target_kind)', ' -> CONTENT_VERSION(version_id, kind)', 'UK (match_id, target_version_id)', 'alg_version : required, reproducible', 'score / mandatory result / timestamp']),
 'MATCH_INPUT_SKILL': ('comparison', ['KEY (match_id, skill_id)', 'FK match_id -> MATCH_RESULT', 'FK skill_id -> SKILL', 'level_used : saved input snapshot']),
 'MATCH_SKILL_RESULT': ('comparison', ['KEY (match_id, skill_id)', 'FK (match_id, target_version_id)', ' -> MATCH_RESULT', 'FK (target_version_id, skill_id)', ' -> CONTENT_REQUIREMENT', 'FK skill_id -> SKILL [redundant link]']),
 'RECOMMENDATION': ('comparison', ['PK recommendation_id : UUID', 'FK match_id -> MATCH_RESULT', 'FK (resource_version_id, resource_kind)', ' -> CONTENT_VERSION(version_id, kind)', 'UK (match_id, resource_version_id)', "CHECK kind IN ('course', 'resource')"]),
 'AUDIT_EVENT': ('comparison', ['PK event_id : UUID', 'FK actor_account_id -> ACCOUNT [nullable]', 'FK subject_account_id -> ACCOUNT [nullable]', 'FK content_version_id -> CONTENT_VERSION', ' [nullable]', 'event_type / occurred_at / minimal metadata']),
}
# Each relationship runs from referenced parent to referencing child. Parent-end
# count is the number of parents per child; child-end count is children per parent.
REL = [
 ('A1','ACCOUNT','STUDENT','1','0..1','account_id','CASCADE','Implemented'),
 ('A2','ACCOUNT','ACCOUNT_ROLE','1','0..*','account_id (recipient)','CASCADE','Implemented'),
 ('A3','ROLE','ACCOUNT_ROLE','1','0..*','role_id','PROTECT','Implemented'),
 ('A4','ACCOUNT','ACCOUNT_ROLE','0..1','0..*','assigned_by (assigner)','SET_NULL','Implemented'),
 ('A5','STUDENT','STUDENT_SKILL','1','0..*','student_id','CASCADE','Proposed'),
 ('A6','SKILL','STUDENT_SKILL','1','0..*','skill_id','PROTECT; retire skill','Proposed'),
 ('A7','STUDENT','STUDENT_COURSE','1','0..*','student_id','CASCADE','Proposed'),
 ('A8','CONTENT_ITEM','STUDENT_COURSE','1','0..*','(course_item_id, course_kind) -> (item_id, kind)','PROTECT; retire item','Proposed'),
 ('R1','CONTENT_ITEM','CONTENT_VERSION','1','0..*','(item_id, kind)','PROTECT; retire item','Proposed'),
 ('R2','ACCOUNT','CONTENT_VERSION','1','0..*','created_by','PROTECT attribution','Proposed'),
 ('R3','ACCOUNT','CONTENT_VERSION','0..1','0..*','published_by','PROTECT attribution','Proposed'),
 ('R4','CONTENT_VERSION','CONTENT_REVIEW','1','0..*','version_id','PROTECT history','Proposed'),
 ('R5','ACCOUNT','CONTENT_REVIEW','1','0..*','reviewer_id','PROTECT attribution','Proposed'),
 ('R6','CONTENT_VERSION','CONTENT_REQUIREMENT','1','0..*','(version_id, kind); career/job only','PROTECT history','Proposed'),
 ('R7','SKILL','CONTENT_REQUIREMENT','1','0..*','skill_id','PROTECT; retire skill','Proposed'),
 ('R8','CONTENT_VERSION','CONTENT_SKILL','1','0..*','(version_id, kind); course/resource only','PROTECT history','Proposed'),
 ('R9','SKILL','CONTENT_SKILL','1','0..*','skill_id','PROTECT; retire skill','Proposed'),
 ('R10','CONTENT_VERSION','CONTENT_SOURCE','1','0..*','version_id','PROTECT published history','Proposed'),
 ('R11','REFERENCE_SOURCE','CONTENT_SOURCE','1','0..*','source_id','PROTECT referenced source','Proposed'),
 ('R12','CONTENT_VERSION','CONTENT_DETAILS','1','0..1','(version_id, kind); version_id unique','PROTECT published history','Proposed'),
 ('R13','COMPANY','CONTENT_DETAILS','0..1','0..*','company_id; job details only','PROTECT referenced company','Proposed'),
 ('C1','STUDENT','MATCH_RESULT','1','0..*','student_id','Private-data deletion workflow','Proposed'),
 ('C2','CONTENT_VERSION','MATCH_RESULT','1','0..*','(target_version_id, target_kind); career/job','PROTECT compared version','Proposed'),
 ('C3','MATCH_RESULT','MATCH_INPUT_SKILL','1','0..*','match_id','CASCADE with private result','Proposed'),
 ('C4','SKILL','MATCH_INPUT_SKILL','1','0..*','skill_id','PROTECT historical input','Proposed'),
 ('C5','MATCH_RESULT','MATCH_SKILL_RESULT','1','0..*','(match_id, target_version_id)','CASCADE with private result','Proposed'),
 ('C6','CONTENT_REQUIREMENT','MATCH_SKILL_RESULT','1','0..*','(target_version_id, skill_id) -> (version_id, skill_id)','PROTECT requirement history','Proposed'),
 ('C7','SKILL','MATCH_SKILL_RESULT','1','0..*','skill_id (redundant when C6 enforced)','PROTECT; optional direct FK','Proposed'),
 ('C8','MATCH_RESULT','RECOMMENDATION','1','0..*','match_id','CASCADE with private result','Proposed'),
 ('C9','CONTENT_VERSION','RECOMMENDATION','1','0..*','(resource_version_id, resource_kind); course/resource','PROTECT recommended version','Proposed'),
 ('D1','ACCOUNT','AUDIT_EVENT','0..1','0..*','actor_account_id','SET_NULL; preserve minimal event','Proposed'),
 ('D2','ACCOUNT','AUDIT_EVENT','0..1','0..*','subject_account_id','SET_NULL; preserve minimal event','Proposed'),
 ('D3','CONTENT_VERSION','AUDIT_EVENT','0..1','0..*','content_version_id','SET_NULL; preserve minimal event','Proposed'),
]
# Explicit routing keeps each focused view readable; repeated boxes are references
# to the same physical entity, not additional tables. Values are x,y,width,height.
PAGES = [
 ('01-accounts-roles','Accounts, profiles, and roles',
  'A1-A4 match the implemented Django relationships. Application tables only.',
  {'role':('ROLE',80,180,350,150),'account':('ACCOUNT',80,650,440,220),'assignment':('ACCOUNT_ROLE',850,180,570,240),'student':('STUDENT',850,650,570,180)},
  [('A3','role','assignment',[(430,250),(850,250)],(620,225)),
   ('A2','account','assignment',[(520,700),(650,700),(650,290),(850,290)],(650,480)),
   ('A4','account','assignment',[(300,650),(300,520),(1500,520),(1500,330),(1420,330)],(1110,520)),
   ('A1','account','student',[(520,780),(850,780)],(680,755))]),
 ('02-student-inputs','Student skills and selected courses',
  'Proposed next section. Selected courses reference stable course items, not job or career items.',
  {'student':('STUDENT',610,170,400,180),'ss':('STUDENT_SKILL',70,170,450,230),'sc':('STUDENT_COURSE',1120,170,410,230),'skill':('SKILL',70,650,450,180),'item':('CONTENT_ITEM',1120,650,410,220)},
  [('A5','student','ss',[(610,250),(520,250)],(560,225)),
   ('A6','skill','ss',[(295,650),(295,400)],(330,530)),
   ('A7','student','sc',[(1010,250),(1120,250)],(1065,225)),
   ('A8','item','sc',[(1325,650),(1325,400)],(1360,530))]),
 ('03-content-lifecycle','Content identity, versions, and review',
  'Allow multiple versions per item. Review approval must match the current draft revision.',
  {'item':('CONTENT_ITEM',70,170,500,220),'version':('CONTENT_VERSION',70,620,500,310),'account':('ACCOUNT',1050,170,480,220),'review':('CONTENT_REVIEW',1050,620,480,250)},
  [('R1','item','version',[(320,390),(320,620)],(355,510)),
   ('R2','account','version',[(1050,250),(900,250),(900,650),(570,650)],(900,480)),
   ('R3','account','version',[(1050,300),(800,300),(800,710),(570,710)],(800,520)),
   ('R4','version','review',[(570,820),(1050,820)],(810,795)),
   ('R5','account','review',[(1300,390),(1300,620)],(1335,510))]),
 ('04-reference-mappings','Reference requirements, sources, and details',
  'Typed version links must enforce matching kind. Details are one-to-zero-or-one, not one-to-many.',
  {'version':('CONTENT_VERSION',620,150,400,310),'skill':('SKILL',70,150,370,180),'source':('REFERENCE_SOURCE',1130,150,400,150),'req':('CONTENT_REQUIREMENT',70,600,440,250),'mapping':('CONTENT_SKILL',70,1000,440,250),'source_link':('CONTENT_SOURCE',1130,600,400,200),'details':('CONTENT_DETAILS',620,1000,400,250),'company':('COMPANY',1130,1000,400,160)},
  [('R6','version','req',[(620,250),(550,250),(550,680),(510,680)],(550,490)),
   ('R7','skill','req',[(270,330),(270,600)],(305,470)),
   ('R8','version','mapping',[(620,300),(580,300),(580,1080),(510,1080)],(580,890)),
   ('R9','skill','mapping',[(70,240),(25,240),(25,1080),(70,1080)],(40,900)),
   ('R10','version','source_link',[(1020,250),(1080,250),(1080,670),(1130,670)],(1080,480)),
   ('R11','source','source_link',[(1330,300),(1330,600)],(1365,450)),
   ('R12','version','details',[(820,460),(820,1000)],(855,780)),
   ('R13','company','details',[(1130,1080),(1020,1080)],(1075,1055))]),
 ('05-comparison-inputs','Comparison ownership, target, and input snapshot',
  'Pin the exact published career/job version. Snapshot inputs do not reference mutable STUDENT_SKILL rows.',
  {'student':('STUDENT',70,170,400,180),'version':('CONTENT_VERSION',1130,170,400,310),'match':('MATCH_RESULT',610,550,430,310),'input':('MATCH_INPUT_SKILL',610,1100,430,210),'skill':('SKILL',70,1100,400,180)},
  [('C1','student','match',[(470,250),(760,250),(760,550)],(620,225)),
   ('C2','version','match',[(1130,250),(900,250),(900,550)],(900,450)),
   ('C3','match','input',[(825,860),(825,1100)],(860,980)),
   ('C4','skill','input',[(470,1180),(610,1180)],(540,1155))]),
 ('06-outcomes-recommendations','Requirement outcomes and recommended resources',
  'An outcome must reference a requirement for the same target version as its match. C7 is logically redundant.',
  {'match':('MATCH_RESULT',70,170,450,310),'req':('CONTENT_REQUIREMENT',1130,170,400,250),'skill':('SKILL',1130,700,400,180),'outcome':('MATCH_SKILL_RESULT',610,700,430,290),'recommendation':('RECOMMENDATION',70,1150,500,290),'version':('CONTENT_VERSION',1030,1150,500,310)},
  [('C5','match','outcome',[(520,250),(740,250),(740,700)],(740,560)),
   ('C6','req','outcome',[(1130,250),(930,250),(930,700)],(930,560)),
   ('C7','skill','outcome',[(1130,770),(1040,770)],(1085,745)),
   ('C8','match','recommendation',[(295,480),(295,1150)],(330,990)),
   ('C9','version','recommendation',[(1030,1230),(570,1230)],(800,1205))]),
 ('07-audit','Audit actor, subject, and content references',
  'The two ACCOUNT boxes are aliases of one table. Nullable links support system events and retained history.',
  {'actor':('ACCOUNT',70,170,400,220),'subject':('ACCOUNT',1130,170,400,220),'audit':('AUDIT_EVENT',610,550,430,290),'version':('CONTENT_VERSION',610,1050,430,310)},
  [('D1','actor','audit',[(470,250),(760,250),(760,550)],(620,225)),
   ('D2','subject','audit',[(1130,250),(930,250),(930,550)],(930,450)),
   ('D3','version','audit',[(825,1050),(825,840)],(860,950))]),
]


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    relations = {r[0]: r for r in REL}
    assert len(relations) == len(REL) == 33
    used = []
    mxfile = ET.Element('mxfile', host='app.diagrams.net', type='device')
    scenes = []
    for slug,title,subtitle,vertices,edges in PAGES:
        svg=[]
        def emit(s): svg.append(s)
        emit('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1600" viewBox="0 0 1600 1600" role="img">')
        emit(f'<title>{html.escape(title)}</title><desc>{html.escape(subtitle)}</desc>')
        emit('<rect width="1600" height="1600" fill="#f8fafc"/>')
        shapes=[]
        def text(x,y,value,size=18,bold=False,color='#162b40',anchor='start'):
            emit(f'<text x="{x}" y="{y}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}" text-anchor="{anchor}">{html.escape(value)}</text>')
            shapes.append(('text',x,y,value,size,bold,color,anchor))
        def rect(x,y,w,h,fill,stroke='#64748b',radius=0):
            emit(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')
            shapes.append(('rect',x,y,w,h,fill,stroke,radius))
        text(60,57,'COMPASS  /  RELATIONSHIP REVIEW',18,True,'#52677a')
        text(60,105,title,32,True)
        text(60,140,subtitle,16)
        # Draw.io vertices use the same coordinates as the SVG export.
        diagram=ET.SubElement(mxfile,'diagram',id=slug,name=title)
        model=ET.SubElement(diagram,'mxGraphModel',dx='1600',dy='1600',grid='1',gridSize='10',page='1',pageWidth='1600',pageHeight='1600')
        root=ET.SubElement(model,'root')
        ET.SubElement(root,'mxCell',id='0')
        ET.SubElement(root,'mxCell',id='1',parent='0')
        def label_cell(id_,value,x,y,w,h,size=18,bold=False):
            c=ET.SubElement(root,'mxCell',id=id_,value=value,style=f'text;html=0;align=left;verticalAlign=middle;fontSize={size};fontStyle={1 if bold else 0};whiteSpace=wrap;overflow=hidden;',vertex='1',parent='1')
            ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        label_cell('title',title,60,65,1480,45,32,True)
        label_cell('subtitle',subtitle,60,115,1480,40,16)
        for rid,source,target,points,label in edges:
            r=relations[rid]
            assert vertices[source][0] == r[1] and vertices[target][0] == r[2], rid
            used.append(rid)
            color='#356b9a' if rid.startswith('A') else '#357942' if rid.startswith('R') else '#b56b15'
            emit('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="2.5"/>')
            shapes.append(('line',points,color))
            # Explicit cardinality labels avoid ambiguous/misread crow's feet.
            short = len(points) == 2 and points[0][1] == points[1][1] and abs(points[0][0]-points[1][0]) < 200
            for end_index,(p,q,card) in enumerate([(points[0],points[1],r[3]),(points[-1],points[-2],r[4])]):
                dx=q[0]-p[0]; dy=q[1]-p[1]
                cx=p[0]+(30 if dx>0 else -30 if dx<0 else 0)
                cy=p[1]+(30 if dy>0 else -30 if dy<0 else -16)
                if dx==0: cx+=30
                if short: cy=p[1]+(-16 if end_index==0 else 28)
                rect(cx-26,cy-17,52,25,'#f8fafc','#f8fafc',3)
                text(cx,cy+2,card,17,True,color,'middle')
                label_cell(f'{rid}-card-{len(root)}',card,cx-26,cy-20,55,28,17,True)
            lx,ly=label
            if short: ly=points[0][1]-52
            rect(lx-24,ly-18,48,26,'#ffffff',color,4)
            text(lx,ly+2,rid,17,True,color,'middle')
            c=ET.SubElement(root,'mxCell',id=rid,value=rid,style=f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=none;startArrow=none;strokeColor={color};strokeWidth=2;fontSize=17;labelBackgroundColor=#ffffff;',edge='1',parent='1',source=source,target=target)
            g=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
            source_v=vertices[source]; target_v=vertices[target]
            # Pin connection endpoints so moving one edge does not choose a new side.
            style=c.get('style')
            style+=f'exitX={(points[0][0]-source_v[1])/source_v[3]};exitY={(points[0][1]-source_v[2])/source_v[4]};exitPerimeter=0;'
            style+=f'entryX={(points[-1][0]-target_v[1])/target_v[3]};entryY={(points[-1][1]-target_v[2])/target_v[4]};entryPerimeter=0;'
            c.set('style',style)
            arr=ET.SubElement(g,'Array',attrib={'as':'points'})
            for x,y in points[1:-1]: ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
        for alias,(entity,x,y,w,h) in vertices.items():
            group,fields=NODES[entity]
            assert 62+len(fields)*28 <= h, (slug,entity,'text overflow')
            rect(x,y,w,h,'#ffffff','#64748b',8)
            rect(x,y,w,42,COLORS[group],'#64748b',0)
            text(x+16,y+28,entity,20,True)
            for i,line in enumerate(fields): text(x+16,y+70+i*28,line,16)
            # HTML labels remain editable text in draw.io, not embedded images.
            value='<b>'+html.escape(entity)+'</b><br><br>'+'<br>'.join(html.escape(f) for f in fields)
            c=ET.SubElement(root,'mxCell',id=alias,value=value,style=f'rounded=1;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacing=14;fontFamily=Arial;fontSize=16;fillColor={COLORS[group]};strokeColor=#64748b;',vertex='1',parent='1')
            ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        footer='Counts at an endpoint describe how many of that entity relate to one entity at the opposite end.'
        text(60,1510,footer,17)
        text(60,1540,'1 = exactly one   |   0..1 = optional one   |   0..* = zero or many   |   IDs link to relationships.md',17)
        text(60,1570,'PROPOSAL ONLY  /  Keys and relationships shown; full non-key attributes remain in the supplied PNG.',16,True)
        label_cell('legend',footer+'\n1 = exactly one | 0..1 = optional one | 0..* = zero or many\nPROPOSAL ONLY. See relationships.md and the ERD review notes.',60,1490,1480,95,17)
        emit('</svg>')
        (OUT/(slug+'.svg')).write_text('\n'.join(svg)+'\n')
        scenes.append({'slug':slug,'title':title,'shapes':shapes})
    assert sorted(used)==sorted(relations), 'Every FK must be drawn exactly once across pages.'
    target=ROOT/'docs/architecture/Compass ERD Relationships.drawio'
    ET.indent(mxfile)
    ET.ElementTree(mxfile).write(target,encoding='utf-8',xml_declaration=True)
    lines=['# ERD relationship catalog','',
           'Proposed relationship completion, November 1, 2026. A1-A4 are implemented; all other relationships are design proposals. No schema changes are applied.',
           '', 'Each row runs from referenced parent to referencing child. The counts state parents per child and children per parent, respectively. Child minimum zero allows drafts and unused reference rows; publication/completion rules can require more.',
           '', '| ID | Parent | Child | Parents per child | Children per parent | FK in child | Parent deletion policy | Status |',
           '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for rid,parent,child,pc,cc,fk,delete,status in REL:
        lines.append(f'| {rid} | {parent} | {child} | {pc} | {cc} | `{fk}` | {delete} | {status} |')
    lines+=['', 'Deletion policies beyond A1-A4 are proposals for the team, not applied database constraints. Private-result deletion needs an explicit lifecycle. PROTECT preserves referenced history; draft-only cleanup needs deliberate service ordering. See the review note for composite-FK and publication enforcement.', '', '## Diagram views','']
    for slug,title,*_ in PAGES:
        lines += [f'### {title}', '', f'![{title}]({slug}.svg)', '']
    (OUT/'relationships.md').write_text('\n'.join(lines)+'\n')
    Path('/tmp/compass-erd-scenes.json').write_text(json.dumps(scenes))
    print(f'Built {len(NODES)} entity definitions, {len(REL)} relationships, {len(PAGES)} SVG views and an editable draw.io document.')


if __name__ == '__main__':
    build()
