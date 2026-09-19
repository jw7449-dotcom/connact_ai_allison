import re

from ..schemas import SECTORS

SECTOR_ALIASES = {
    "Investment Banking": ("investment banking", "投行", "投资银行", " ib ", "m&a"),
    "Private Equity": ("private equity", "私募股权", "私募", " pe "),
    "Asset Management": ("asset management", "资产管理", "资管", "buy side", "买方"),
    "Venture Capital": ("venture capital", "风险投资", "风投", "创投", " vc "),
    "Risk Management": ("risk management", "风险管理", "风控"),
}
CITIES = {
    "New York": ("new york", "nyc", "纽约"),
    "London": ("london", "伦敦"),
    "Hong Kong": ("hong kong", "hk", "香港"),
    "Singapore": ("singapore", "新加坡"),
    "San Francisco": ("san francisco", "sf", "旧金山", "三藩"),
    "Shanghai": ("shanghai", "上海"),
    "Beijing": ("beijing", "北京"),
    "Shenzhen": ("shenzhen", "深圳"),
    "Tokyo": ("tokyo", "东京"),
    "Chicago": ("chicago", "芝加哥"),
    "Boston": ("boston", "波士顿"),
    "Los Angeles": ("los angeles", " la ", "洛杉矶"),
}
SENIORITY = {
    "Junior": ("junior", "初级", "初阶"),
    "Senior": ("senior", "资深", "高级"),
    "Intern": ("intern", "实习"),
    "Vice President": ("vice president", " vp ", "副总裁"),
    "Managing Director": ("managing director", " md ", "董事总经理"),
    "Director": ("director", "总监"),
    "Partner": ("partner", "合伙人"),
}
ROLES = {
    "Analyst": ("analyst", "分析师", "分析员"),
    "Associate": ("associate", "经理", "associate"),
    "Portfolio Manager": ("portfolio manager", "基金经理"),
    "Trader": ("trader", "交易员"),
    "Recruiter": ("recruiter", "招聘"),
    "Engineer": ("engineer", "工程师"),
}
THEMES = {
    "TMT": ("tmt", "科技传媒", "科技媒体"),
    "M&A": ("m&a", "mergers", "并购"),
    "Fintech": ("fintech", "金融科技"),
    "Healthcare": ("healthcare", "医疗", "医药"),
    "Semiconductor": ("semiconductor", "半导体", "芯片"),
    "Crypto": ("crypto", "blockchain", "加密", "区块链"),
    "AI": ("artificial intelligence", "人工智能"),
    "ESG": ("esg", "可持续"),
    "IPO": ("ipo", "上市"),
    "Consumer": ("consumer", "消费"),
    "Energy": ("energy", "能源"),
    "Real Estate": ("real estate", "房地产", "地产"),
}
CN_DIGITS = {
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _hit(haystack, needles):
    return any(n in haystack for n in needles)


def _requested_count(text):
    digits = re.search(r"\b(\d{1,3})\b", text)
    if digits:
        return int(digits.group(1))
    cn = re.search(r"([一两二三四五六七八九十]+)\s*(?:个|位|名|人)", text)
    if cn:
        word = cn.group(1)
        if word == "十":
            return 10
        if word.startswith("十"):
            return 10 + CN_DIGITS.get(word[1:], 0)
        if word.endswith("十"):
            return CN_DIGITS.get(word[0], 1) * 10
        return CN_DIGITS.get(word[0], 0)
    return 0


def heuristic_intent(prompt, language):
    """Offline intent parsing. Mock mode must stay useful without an AI provider."""
    text = " " + prompt.lower() + " "
    sector = next((s for s in SECTORS if _hit(text, SECTOR_ALIASES[s])), "")
    location = next((c for c, aliases in CITIES.items() if _hit(text, aliases)), "")
    rank = next((r for r, aliases in SENIORITY.items() if _hit(text, aliases)), "")
    role = next((r for r, aliases in ROLES.items() if _hit(text, aliases)), "")
    themes = [t for t, aliases in THEMES.items() if _hit(text, aliases)]
    title = " ".join(p for p in (rank, role) if p)
    zh = language == "zh"
    where = location or ("不限地区" if zh else "any location")
    who = title or ("专业人士" if zh else "professionals")
    summary = (
        f"在{where}搜索{who}" if zh else f"Searching for {who} in {where}"
    )
    return {
        "title": title,
        "company": "",
        "location": location,
        "keywords": " ".join(themes),
        "sector": sector,
        "per_page": _requested_count(text),
        "summary": summary,
    }


def normalize_intent(raw, prompt):
    """Coerce provider output into SearchInput's contract. Never trust it as-is."""
    raw = raw if isinstance(raw, dict) else {}

    def text(key, limit):
        value = raw.get(key)
        return value.strip()[:limit] if isinstance(value, str) else ""

    sector = text("sector", 60)
    count = raw.get("per_page")
    # 0 means the request never named a number, so fall back to a full page.
    count = count if isinstance(count, int) and count > 0 else 10
    filters = {
        "title": text("title", 200),
        "company": text("company", 200),
        "location": text("location", 200),
        "keywords": text("keywords", 300),
        # An unrecognized industry belongs in keywords, not in the strict enum.
        "sector": sector if sector in SECTORS else "",
        "per_page": min(max(count, 1), 10),
    }
    if sector and sector not in SECTORS:
        filters["keywords"] = (filters["keywords"] + " " + sector).strip()[:300]
    if not any(filters[k] for k in ("title", "company", "location", "keywords", "sector")):
        filters["keywords"] = prompt.strip()[:300]
    return {**filters, "summary": text("summary", 200)}
