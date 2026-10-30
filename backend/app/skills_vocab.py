"""Skill vocabulary shared by every resume.

COMMON_SKILLS lets the fit score see skills a posting asks for that the resume does not list, so
"missing" can name them. SYNONYMS maps a canonical skill to other spellings postings use.
CASE_SENSITIVE holds names that are also ordinary English words ("react to", "excel in", "a slate
of"); they only count when capitalised as written here.
"""

SYNONYMS: dict[str, tuple[str, ...]] = {
    "JavaScript": ("JS", "ECMAScript"),
    "TypeScript": ("TS",),
    "PostgreSQL": ("Postgres",),
    "Kubernetes": ("k8s",),
    "Node.js": ("NodeJS", "Node"),
    "React": ("React.js", "ReactJS"),
    "Vue": ("Vue.js", "VueJS"),
    "Angular": ("AngularJS",),
    "Go": ("Golang",),
    "C#": ("C Sharp",),
    ".NET": ("dotnet", "ASP.NET", ".NET Core"),
    "Amazon Web Services": ("AWS",),
    "Microsoft Azure": ("Azure",),
    "Google Cloud": ("GCP", "Google Cloud Platform"),
    "Machine learning": ("ML",),
    "Artificial intelligence": ("AI",),
    "Continuous integration": ("CI/CD",),
    "REST APIs": ("REST", "RESTful", "RESTful APIs", "REST API"),
    "Microsoft SQL Server": ("SQL Server", "MSSQL", "T-SQL"),
    "Power BI": ("PowerBI",),
    "Excel": ("Microsoft Excel", "MS Excel"),
    "HTML": ("HTML5",),
    "CSS": ("CSS3",),
    "Git": ("GitHub", "GitLab"),
    "Linux": ("Unix",),
    "Bash": ("shell scripting",),
    "Tableau": (),
    "Ellucian Banner": ("Banner",),
}

COMMON_SKILLS: tuple[str, ...] = (
    # Languages
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "Rust", "Ruby", "PHP",
    "Perl", "R", "SAS", "Stata", "SPSS", "MATLAB", "Scala", "Kotlin", "Swift", "Objective-C",
    "Visual Basic", "VBA", "COBOL", "Fortran", "SQL", "PL/SQL", "Bash", "PowerShell", "HTML", "CSS",
    # Frameworks and front end
    "React", "Angular", "Vue", "Svelte", "Next.js", "Node.js", "Express", "Django", "Flask",
    "FastAPI", "Spring", "Spring Boot", "Laravel", "Rails", ".NET", "jQuery", "Bootstrap",
    "Tailwind CSS", "Sass", "WordPress", "Drupal", "Cascade", "TerminalFour", "OmniUpdate",
    # Data and databases
    "MySQL", "PostgreSQL", "Oracle", "Microsoft SQL Server", "SQLite", "MongoDB", "Redis",
    "Snowflake", "Databricks", "Spark", "Hadoop", "Kafka", "Airflow", "dbt", "ETL", "Tableau",
    "Power BI", "Looker", "Qlik", "Excel", "Argos", "Cognos", "Informatica", "SSIS", "SSRS",
    "pandas", "NumPy", "scikit-learn", "TensorFlow", "PyTorch", "Machine learning",
    "Artificial intelligence", "Data visualization", "Data warehousing", "Statistics",
    # Cloud, infrastructure, DevOps
    "Amazon Web Services", "Microsoft Azure", "Google Cloud", "Docker", "Kubernetes", "Terraform",
    "Ansible", "Jenkins", "GitHub Actions", "Continuous integration", "Linux", "Windows Server",
    "Active Directory", "VMware", "Networking", "TCP/IP", "DNS", "Firewalls", "Okta", "Entra ID",
    "Microsoft 365", "Intune", "Jamf", "ServiceNow", "Splunk",
    # Practices and tools
    "Git", "Jira", "Agile", "Scrum", "REST APIs", "GraphQL", "Microservices", "Unit testing",
    "Selenium", "Playwright", "Accessibility", "WCAG", "UX design", "Figma",
    # Higher-education enterprise systems
    "Ellucian Banner", "Colleague", "PeopleSoft", "Workday", "Salesforce", "Slate", "Canvas",
    "Blackboard", "Moodle", "D2L", "Kuali", "Jenzabar", "Anthology", "Modern Campus",
    "Ellucian Ethos", "Degree Works", "Navigate", "TargetX",
)

CASE_SENSITIVE: frozenset[str] = frozenset({
    "React", "Go", "R", "C", "Swift", "Rust", "Spark", "Express", "Excel", "Spring", "Rails",
    "Oracle", "Banner", "Slate", "Workday", "Canvas", "Navigate", "Colleague", "Anthology",
    "Cascade", "Node", "Statistics", "Networking", "Accessibility", "Looker", "Argos", "Okta",
})
