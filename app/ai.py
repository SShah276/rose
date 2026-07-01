import os
import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it as an environment variable (e.g. set ANTHROPIC_API_KEY=sk-ant-...)."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _format_profile(p: dict) -> str:
    lines = []
    if p.get("name"):
        lines.append(f"Name: {p['name']}")
    if p.get("email"):
        lines.append(f"Email: {p['email']}")
    if p.get("school"):
        lines.append(
            f"School: {p['school']} | {p.get('degree','')} | "
            f"Grad: {p.get('graduation_year','')} | GPA: {p.get('gpa','')}"
        )
    if p.get("personal_summary"):
        lines.append(f"\nSummary:\n{p['personal_summary']}")
    if p.get("skills"):
        lines.append(f"\nSkills:\n{p['skills']}")
    if p.get("experience"):
        lines.append(f"\nExperience:\n{p['experience']}")
    if p.get("projects"):
        lines.append(f"\nProjects:\n{p['projects']}")
    if p.get("strongest_bullets"):
        lines.append(f"\nStrongest Resume Bullets:\n{p['strongest_bullets']}")
    if p.get("preferred_roles"):
        lines.append(f"\nPreferred Roles: {p['preferred_roles']}")

    resume_lines = []
    for i in range(1, 5):
        name = p.get(f"resume_v{i}_name", "").strip()
        if name:
            resume_lines.append(f"  v{i}: {name}")
    if resume_lines:
        lines.append("\nResume Versions:\n" + "\n".join(resume_lines))

    return "\n".join(lines) or "No candidate profile set up yet."


_SYSTEM_BASE = """\
You are an expert career advisor helping a CS/engineering student land top tech internships.
You have deep knowledge of what top companies look for in interns.

Rules:
- Be specific: reference the candidate's actual skills and projects, not generic advice
- Be actionable: concrete things they can say or do
- Be honest: call out real gaps, not just positives
- Be concise: no filler or padding"""


def generate_job_analysis(job: dict, profile: dict) -> str:
    client = _get_client()
    system = _SYSTEM_BASE + f"\n\nCandidate Profile:\n{_format_profile(profile)}"

    prompt = f"""Analyze this internship opportunity.

Company: {job.get('company', '?')}
Title: {job.get('title', '?')}
Location: {job.get('location', '?')}
Role Type: {job.get('role_type', '?')}
Description: {job.get('description') or 'Not provided'}

Write exactly these sections:

## Key Requirements
(3–5 bullets of what the role actually demands)

## Matched Skills
(Candidate's specific skills/experiences that directly apply — reference them by name)

## Skill Gaps
(What they're missing or could strengthen before applying)

## Fit Assessment
(2–3 sentences: strength of match and what angle to take in the application)

## Resume Recommendation
(Which resume version fits best and one-line reason)"""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def generate_cover_letter(job: dict, profile: dict, template: str | None = None) -> str:
    client = _get_client()
    system = _SYSTEM_BASE + f"\n\nCandidate Profile:\n{_format_profile(profile)}"

    if template and template.strip():
        prompt = f"""I have a cover letter I wrote that captures my exact voice, tone, and experiences. \
Adapt it for a new job application while preserving my writing style as closely as possible.

MY ORIGINAL COVER LETTER:
---
{template.strip()}
---

NEW JOB:
Company: {job.get('company', '?')}
Title: {job.get('title', '?')}
Role Type: {job.get('role_type', '?')}
Description: {job.get('description') or 'Not provided'}

Instructions:
- Keep my sentence structure, vocabulary, and tone intact wherever possible
- Replace company-specific names/references with the new company name
- Update role title and department references to match the new job
- Keep all personal experiences and projects — only re-frame if the new role demands it
- Adjust the opening hook so it speaks to THIS company's industry or mission
- Match the original approximate length

CRITICAL OUTPUT FORMAT:
- Output ONLY the letter body paragraphs — nothing else
- Do NOT write "Here is the adapted cover letter", "---", or any prefix/preamble
- Do NOT add notes, feedback, suggestions, or commentary after the letter
- Do NOT include a date, address, salutation, or sign-off — those are added separately
- Just the paragraphs, separated by a blank line"""
        max_tokens = 900
    else:
        prompt = f"""Write a cover letter for this internship application.

Company: {job.get('company', '?')}
Title: {job.get('title', '?')}
Role Type: {job.get('role_type', '?')}
Description: {job.get('description') or 'Not provided'}

Requirements:
- 3 paragraphs, max 280 words total
- P1: specific hook about why THIS company (not generic excitement)
- P2: single most relevant project or experience with a concrete result or metric
- P3: concise skills alignment + genuine closing (no "I look forward to hearing from you")
- First person, professional but not stiff
- Do NOT start with "I am writing to apply for..."

Output only the letter body — no salutation, no headers, no sign-off."""
        max_tokens = 600

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def generate_contact_outreach(job: dict, contact: dict, relationship_type: str, profile: dict) -> str:
    """Personalized message to a specific contact about a specific job."""
    client = _get_client()
    system = _SYSTEM_BASE + f"\n\nCandidate Profile:\n{_format_profile(profile)}"

    rel_map = {
        "recruiter":       "a company recruiter",
        "hiring_manager":  "the hiring manager for this role",
        "engineer":        "a software engineer on the team",
        "alumni":          "a university alumnus who works there",
        "hr":              "an HR professional",
    }
    rel_desc = rel_map.get(relationship_type, "a professional contact")

    prompt = f"""Write an outreach message to {rel_desc} about an internship.

Contact:
Name: {contact.get('name', '?')}
Title: {contact.get('title') or 'Unknown'}
Company: {contact.get('company', '?')}

Job:
Title: {job.get('title', '?')}
Company: {job.get('company', '?')}
Role Type: {job.get('role_type', '?')}

Generate two versions separated by "---":

**LinkedIn Message** (under 300 characters, no line breaks)
[Address by first name. Reference their specific role. One clear ask.]

---

**Email**
Subject: [concise subject line]

[P1: specific hook — something about them, their work, or the company that's not generic]
[P2: your single most relevant experience/project in 2 sentences with a concrete result]
[P3: clear one-sentence ask]

Rules: No "I hope this message finds you well." No "I came across your profile." No "I am very passionate about." Be direct and warm."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def generate_outreach(job: dict, profile: dict) -> str:
    client = _get_client()
    system = _SYSTEM_BASE + f"\n\nCandidate Profile:\n{_format_profile(profile)}"

    prompt = f"""Write three recruiter outreach messages.

Company: {job.get('company', '?')}
Title: {job.get('title', '?')}

Generate exactly these three blocks separated by "---":

**LinkedIn Connection Note**
(Under 300 characters, no line breaks — direct ask to connect about the role)

---

**Cold Email**
Subject: [subject line]

[3 short paragraphs: hook specific to the company, value you bring, clear ask]

---

**Follow-up Email** (send after 1 week of silence)
Subject: [subject line]

[2 paragraphs: brief re-intro, renewed ask with a slight new angle]

Do not use phrases like "I came across your posting", "I am very passionate about", or "I hope this message finds you well."."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text
