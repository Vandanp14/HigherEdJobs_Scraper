"""Early-career rules for Company boards jobs.

These replace the user's Google-style searches (see the Company boards spec), which were:

  site:job-boards.greenhouse.io ("software engineer" OR "software developer") ("new grad" OR "entry level" OR "junior")
  site:jobs.lever.co "software engineer" ("new grad" OR "junior" OR "entry level")
  site:jobs.ashbyhq.com "software engineer" ("new grad" OR "early career")
  site:myworkdayjobs.com ("software engineer I" OR "associate software engineer")
  site:jobs.smartrecruiters.com ("junior software engineer" OR "associate software engineer")
  "software engineer" "new grad" "2027" (apply OR careers)
  "software engineer I" ("0-2 years" OR "new grad") -senior -staff
  "software engineer" ("2026 graduate" OR "2027 graduate" OR "new graduate")
  "associate software engineer" "United States" apply
  "backend engineer" ("junior" OR "new grad" OR "entry level")
  "full stack developer" ("entry level" OR "0-2 years")
  "software engineer" "bachelor's degree" "0 years" -internship
  "software engineer" "H-1B sponsorship" ("entry level" OR "new grad")
  "software engineer" ("OPT" OR "STEM OPT") ("new grad" OR "entry level")
  "software engineer" "visa sponsorship available" careers
  "software engineer" "international students" "2027" careers
  "software engineer" "new grad" -senior -"no sponsorship" -"unable to sponsor"
  ("software engineer I" OR "associate software engineer" OR "new grad software engineer") ("2026" OR "2027") -senior -staff -principal

Sponsorship wording never removes a job here: the sponsorship classifier labels it instead, so a
listing that says nothing about sponsorship is still shown (and never read as eligible).
Edit the patterns below to widen or narrow what is kept.
"""

import re

_I = re.IGNORECASE

# Rule 1: a software role named in the searches.
SOFTWARE_ROLE = re.compile(
    r"\bsoftware\s+(?:engineer|engineering|developer|development\s+engineer)\b"
    r"|\b(?:SDE|SWE)\b"
    r"|\bback[\s-]?end\s+(?:engineer|developer)\b"
    r"|\bfull[\s-]?stack\s+(?:engineer|developer)\b",
    _I,
)

# Rule 2: titles above entry level, or internships.
EXCLUDED_TITLE = re.compile(
    r"\b(?:senior|sr|staff|principal|lead|manager|intern|internship)\b"
    r"|\b(?:engineer|developer|engineering|SDE|SWE)\s*,?\s*(?:II|III|IV|V|2|3|4|5)\b",
    _I,
)

# Rule 3: early-career wording in the title...
EARLY_TITLE = re.compile(
    r"\bnew\s+grad(?:uate)?s?\b|\bjunior\b|\bjr\b|\bentry[\s-]+level\b|\bearly[\s-]+career\b|\bassociate\b"
    r"|\b(?:engineer|developer|SDE|SWE)\s*,?\s*(?:I|1)\b",
    _I,
)
# ...or in the description. "\b0" keeps "10-20 years" and "20 years" from matching.
EARLY_DESCRIPTION = re.compile(
    r"\bnew\s+grad(?:uate)?s?\b|\b20(?:26|27)\s+grad(?:uate)?s?\b"
    r"|\b0\s*(?:-|–|to)\s*2\+?\s*years?\b|\b0\+?\s*years?\b",
    _I,
)

# Rule 4: US, remote or unknown. A location is rejected only when it names somewhere outside the
# US and nothing in the US, so "Toronto, Canada or New York, NY" stays.
_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
US_MARKER = re.compile(
    r"\b(?:united\s+states|usa|u\.s\.a?\.?|new\s+york|san\s+francisco|seattle|boston|chicago|austin|"
    r"los\s+angeles|denver|atlanta|washington|california|texas|massachusetts|illinois|colorado|"
    r"bay\s+area|silicon\s+valley|palo\s+alto|mountain\s+view|san\s+jose|sunnyvale|menlo\s+park|"
    r"pittsburgh|philadelphia|miami|dallas|houston|portland|san\s+diego|raleigh|nashville|phoenix|"
    r"salt\s+lake\s+city|minneapolis|detroit)\b",
    _I,
)
US_CODE = re.compile(r"\bUS\b|,\s*(?:" + "|".join(_STATES) + r")\b")
NON_US = re.compile(
    r"\b(?:canada|united\s+kingdom|england|scotland|ireland|india|israel|germany|france|netherlands|"
    r"poland|spain|portugal|italy|sweden|switzerland|denmark|norway|finland|romania|ukraine|serbia|"
    r"czech|hungary|singapore|japan|china|korea|taiwan|hong\s+kong|philippines|vietnam|indonesia|"
    r"malaysia|australia|new\s+zealand|brazil|mexico|argentina|colombia|chile|costa\s+rica|uruguay|"
    r"egypt|nigeria|kenya|south\s+africa|uae|dubai|turkey|pakistan|bangladesh|"
    r"london|toronto|vancouver|montreal|ottawa|calgary|bengaluru|bangalore|hyderabad|pune|chennai|"
    r"mumbai|delhi|gurugram|gurgaon|noida|dublin|berlin|munich|hamburg|paris|amsterdam|tel\s+aviv|"
    r"yokneam|haifa|warsaw|krakow|tokyo|seoul|sydney|melbourne|sao\s+paulo|são\s+paulo|lisbon|madrid|"
    r"barcelona|zurich|stockholm|copenhagen|prague|bucharest|manila|shanghai|beijing|shenzhen)\b",
    _I,
)
NON_US_CODE = re.compile(r"\b(?:UK|EMEA|APAC|LATAM)\b")

# Workday boards are searched server-side with these, one search each.
WORKDAY_SEARCH_TERMS = ("software engineer", "software developer", "backend engineer", "full stack developer")


def title_candidate(title: str | None) -> bool:
    """Rules 1 and 2: a software role that is not senior, staff, lead, manager or intern."""
    return bool(title) and bool(SOFTWARE_ROLE.search(title)) and not EXCLUDED_TITLE.search(title)


def early_career(title: str | None, description: str | None) -> bool:
    """Rule 3: early-career wording in the title, or in the description."""
    return bool(title and EARLY_TITLE.search(title)) or bool(description and EARLY_DESCRIPTION.search(description))


def location_allowed(location: str | None) -> bool:
    """Rule 4: unknown locations are kept so parsing gaps do not lose jobs."""
    if not location or not location.strip():
        return True
    outside = NON_US.search(location) or NON_US_CODE.search(location)
    inside = US_MARKER.search(location) or US_CODE.search(location)
    return not outside or bool(inside)


def keep_job(title: str | None, location: str | None, description: str | None) -> bool:
    return title_candidate(title) and early_career(title, description) and location_allowed(location)
