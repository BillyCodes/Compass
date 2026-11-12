"""Reviewed, exact O*NET software selections; scoring remains editorial.

Version 2 adds ten occupation-specific examples to the six shared examples.
Names/categories below are Compass normalizations, never O*NET proficiency ratings.
"""
BASE_SKILLS = {'Python': ('Python', 'Programming'), 'Structured query language SQL': ('SQL', 'Data'),
               'PostgreSQL': ('PostgreSQL', 'Data'), 'Git': ('Git', 'Tools'),
               'Linux': ('Linux', 'Systems'), 'Docker': ('Docker', 'Tools')}
EXTRAS = {
    '15-1252.00': ['JavaScript', 'Oracle Java', 'C#', 'C++', 'TypeScript', 'React', 'Node.js', 'Kubernetes', 'Jenkins CI', 'RESTful API'],
    '15-1212.00': ['Splunk Enterprise', 'Tenable Nessus', 'Microsoft PowerShell', 'MITRE ATT&CK software', 'Amazon Web Services AWS software', 'Microsoft Azure software', 'Firewall software', 'UNIX', 'eMASS', 'Wireshark'],
    '15-2051.00': ['R', 'pandas', 'NumPy', 'Scikit-learn', 'TensorFlow', 'PyTorch', 'Apache Spark', 'Apache Hadoop', 'Tableau', 'SAS'],
    '15-1211.00': ['Microsoft Power BI', 'Microsoft Visio', 'ServiceNow', 'SAP software', 'Atlassian JIRA', 'Atlassian Confluence', 'Unified modeling language UML', 'Microsoft Excel', 'JavaScript', 'Amazon Web Services AWS software'],
    '15-1243.00': ['Apache Kafka', 'Apache Spark', 'Snowflake', 'Tableau', 'Microsoft Power BI', 'Oracle Java', 'Amazon Web Services AWS software', 'Microsoft Azure software', 'MySQL', 'Oracle Database'],
}
NORMALIZATIONS = {
    'Oracle Java': ('Java', 'Programming'), 'Microsoft PowerShell': ('PowerShell', 'Systems'),
    'MITRE ATT&CK software': ('MITRE ATT&CK', 'Security'),
    'Amazon Web Services AWS software': ('AWS', 'Cloud'), 'Microsoft Azure software': ('Azure', 'Cloud'),
    'SAP software': ('SAP', 'Enterprise tools'), 'Atlassian JIRA': ('Jira', 'Tools'),
    'Atlassian Confluence': ('Confluence', 'Tools'), 'Unified modeling language UML': ('UML', 'Systems analysis'),
    'Microsoft Power BI': ('Power BI', 'Data'), 'Microsoft Visio': ('Visio', 'Systems analysis'),
    'Microsoft Excel': ('Excel', 'Data'),
}


def selection(code):
    result = dict(BASE_SKILLS)
    for raw in EXTRAS.get(code, []):
        category = {'15-1252.00': 'Development tools', '15-1212.00': 'Security',
                    '15-2051.00': 'Data science', '15-1211.00': 'Systems analysis', '15-1243.00': 'Data'}[code]
        result[raw] = NORMALIZATIONS.get(raw, (raw, category))
    return result


def selected_examples(code, examples):
    mappings = selection(code)
    found = {}
    for row in examples if isinstance(examples, list) else []:
        if not isinstance(row, dict) or row.get('Workplace Example') not in mappings:
            continue
        raw = row['Workplace Example']
        name, category = mappings[raw]
        found[name.casefold()] = dict(raw_name=raw, skill=name, category=category,
            hot=row.get('Hot Technology') == 'Y', demand=row.get('In Demand') == 'Y')
    return sorted(found.values(), key=lambda row: (not row['demand'], row['skill'].casefold()))


def version_suggestions(version):
    """Use the edition's preserved rows, rather than today's CSV or unrelated careers."""
    found = {}
    for link in version.source_links.select_related('source'):
        source = link.source
        if source.provider != 'onet' or source.external_id not in EXTRAS:
            continue
        for row in selected_examples(source.external_id, source.raw_metadata.get('software_examples', [])):
            found[row['skill'].casefold()] = dict(row, source=source)
    return sorted(found.values(), key=lambda row: (not row['demand'], row['skill'].casefold()))
