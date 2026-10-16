import markdown2
import re

EMOJI_MAP = {
    # Status / Alerts
    "✅": "5350486389806868244",  # IslomjonAnime check
    "❌": "5273914604752216432",  # IslomjonAnime cross
    "⚠️": "5213134259098761044",  # Decoration warning/alert
    "⚠": "5213134259098761044",
    "🟢": "5415722549281561774",  # IslomjonAnime green
    "🟡": "5415803109983133508",  # IslomjonAnime yellow
    "🔴": "5416044289576673808",  # IslomjonAnime red
    # Roles
    "👑": "5431684550424011313",  # IslomjonAnime crown
    "⭐": "5361561289397121939",  # IslomjonAnime star
    "👤": "5373012449597335010",  # User
    "👥": "5372926953978341366",  # Users
    "🎓": "5375163339154399459",  # Grad
    "👨‍💻": "5429398777419014515",  # Dev
    # School / Education
    "🏫": "5265002646397285605",  # School
    "📚": "5373098009640836781",  # Books
    "📖": "5226512880362332956",  # Book
    "📗": "5226512880362332956",  # Green book
    # Tools & Controls
    "⚙️": "5213470220030585409",  # Decoration settings
    "⚙": "5213470220030585409",
    "🛠": "5213214428958306222",  # Tools
    "⏰": "5215394081911351762",  # Decoration clock
    "⏳": "5215327832040811010",  # Decoration hourglass
    "🔄": "5264727218734524899",  # Refresh
    "🔑": "5330115548900501467",  # Key
    "🔐": "5350619413533958825",  # Lock
    "✏️": "5334673106202010226",  # Edit
    "✏": "5334673106202010226",
    "🔍": "5188217332748527444",  # Search
    "➕": "5226945370684140473",  # Plus
    # System & Media
    "🖥": "5215186239853964761",  # System
    "💿": "5215352343419167936",  # DB
    "📊": "5431577498364158238",  # Stats
    "📈": "5373001317042101552",  # Chart Up
    "📉": "5361748661640372834",  # Chart Down
    "📝": "5215672443036772796",  # Memo
    "📁": "5215672443036772796",  # Folder/Memo
    "📄": "5215672443036772796",  # Document/Memo
    "📷": "5215685959298853284",  # Camera
    "📸": "5215685959298853284",  # Photo/Camera
    "🔔": "5215372534060428125",  # Bell
    "🔗": "5215391376081954505",  # Link
    "💳": "5213403875670765022",  # Card/Money
    # Celebrations & Highlights
    "🎉": "5215628200578655810",  # Party
    "💎": "5215377245639549895",  # Diamond
    "🎁": "5215440433198413312",  # Gift
    "⚡️": "5215356457997837659",  # Flash
    "⚡": "5215356457997837659",
    "💡": "5215356457997837659",  # Tip
    "🤖": "5312078301165012884",  # Robot
    "💭": "5456125285160226779",  # Thinking
    "🤔": "5456125285160226779",  # Thinking
    "👋": "5472055112702629499",  # Wave
    "📆": "5431897022456145283",  # Calendar
    # Additional Tools, Media & Symbols
    "✨": "5472164874886846699",  # Sparkles
    "🎯": "5350460637182993292",  # Target
    "💻": "5431376038628171216",  # Laptop/Code
    "🗣": "5370765563226236970",  # Speaking
    "📌": "5213260226194583825",  # Pin
    "✍️": "5470060791883374114",  # Writing
    "✍": "5470060791883374114",
    "ℹ️": "5213134259098761044",  # Info/Alert
    "ℹ": "5213134259098761044",
    "🚫": "5273914604752216432",  # Block/Cross
    "🛡": "5350619413533958825",  # Shield/Lock
    "🌐": "5265002646397285605",  # Globe/Web
    "🎧": "5215372534060428125",  # Headphones/Audio
    "💾": "5215352343419167936",  # Floppy/DB
    "📋": "5215672443036772796",  # Clipboard/Memo
    "🗑": "5273914604752216432",  # Trash/Cross
    "🔙": "5406745015365943482",  # Back
    "⬅️": "5406745015365943482",  # Left
    "⬅": "5406745015365943482",
    "➡️": "5406745015365943482",  # Right
    "➡": "5406745015365943482",
}

_EMOJI_REGEX = re.compile('|'.join(re.escape(k) for k in sorted(EMOJI_MAP.keys(), key=len, reverse=True)))


def apply_premium_emojis(html: str) -> str:
    """
    Safely wraps all known emojis with Telegram Custom Animated Emoji links:
    <a href="tg://emoji?id=...">char</a>
    Preserves existing HTML tags and avoids double-wrapping or nested tags.
    """
    if not html:
        return ""
    parts = re.split(r'(<[^>]+>)', html)
    in_emoji_link = False
    for i in range(len(parts)):
        p = parts[i]
        if p.startswith('<'):
            if 'tg://emoji' in p:
                in_emoji_link = True
            elif in_emoji_link and p == '</a>':
                in_emoji_link = False
        else:
            if not in_emoji_link:
                parts[i] = _EMOJI_REGEX.sub(lambda m: f'<a href="tg://emoji?id={EMOJI_MAP[m.group(0)]}">{m.group(0)}</a>', parts[i])
    return ''.join(parts)


def render_styled_text(markdown_text: str) -> str:
    """
    Converts markdown into clean, standard Telegram HTML formatting using markdown2
    and applies animated custom emojis across the text.
    """
    if not markdown_text:
        return ""
    
    # 1. Convert markdown to HTML using markdown2
    html = markdown2.markdown(markdown_text, extras=['fenced-code-blocks'])
    
    # 2. Normalize tags for Telegram HTML
    html = html.replace('<p>', '').replace('</p>', '\n\n')
    html = html.replace('<h1>', '<b>').replace('</h1>', '</b>\n\n')
    html = html.replace('<h2>', '<b>').replace('</h2>', '</b>\n\n')
    html = html.replace('<h3>', '<b>').replace('</h3>', '</b>\n\n')
    html = html.replace('<h4>', '<b>').replace('</h4>', '</b>\n\n')
    html = html.replace('<h5>', '<b>').replace('</h5>', '</b>\n\n')
    html = html.replace('<h6>', '<b>').replace('</h6>', '</b>\n\n')
    html = html.replace('<strong>', '<b>').replace('</strong>', '</b>')
    html = html.replace('<em>', '<i>').replace('</em>', '</i>')
    html = html.replace('<ul>', '').replace('</ul>', '\n')
    html = html.replace('<ol>', '').replace('</ol>', '\n')
    html = html.replace('<li>', '• ').replace('</li>', '\n')
    html = html.replace('<hr />', '\n———\n').replace('<hr>', '\n———\n')
    
    # Clean excessive newlines
    html = re.sub(r'\n{3,}', '\n\n', html)

    # 3. Apply custom animated emojis
    return apply_premium_emojis(html).strip()


if __name__ == '__main__':
    sample = "❌ Tizimga kirib bo'lmadi!\n👤 Login: oishaabdugapporova\n⚠️ Sabab: Xato"
    print("Rendered:\n", apply_premium_emojis(sample))
