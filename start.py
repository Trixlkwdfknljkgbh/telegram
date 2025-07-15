import json
from pathlib import Path
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetChannelsRequest
from telethon.tl.types import InputPeerChannel
from telethon.errors import MessageNotModifiedError
import deepl  # Замість deep_translator
import re

# ⚙️  API-дані ---------------------------------------------------------------
api_id   = 22313648
api_hash = 'd151fa8d664b4bad071fe06be91d7fa6'
translator = deepl.Translator("c3756d4f-c9e0-4d56-b8e6-877aba12ac0d:fx")

# Канали
SOURCE_CHANNEL = None
TARGET_CHANNEL = None

# Ключові слова
KEYWORDS = [
    'плечо', 'Плечо',
    'Что там с Биткоином?',
    'Лимитный ордер'
]

# Фрази для видалення
BLOCK_PHRASES = [
    '🧮 5% От банка',
    '☝🔥Бонус до 35000$ за регистрацию',
    '☝️🔥Бонус до 35000$ за регистрацию  в BYBIT',
    'Promo 51796',
    'Привязка',
    '✅Обучение',
    '📲VIP',
    '🔶',
    '📹',
    '|',
    'Берем',
    'Маржа Кросс',
    'Наши соцсети',
    'Youtube',
    'Inst',
    'TikTok'
]

# Кеш «оригінал → переслане»
MAP_FILE = Path('msg_map.json')
msg_map = MAP_FILE.exists() and json.loads(MAP_FILE.read_text()) or {}

# Сесія
session_str = "1BJWap1wBuyPB5OG6I6jelMmgx48vAdUryt24KR8ijYETgzdEWdRa7AmagbERCwp3LXPQCp-Nz5xVJmGhUWBqGNp4RVn0keuP2OU-UxiqTkplM3iio_3qzrmpRfIWkjGAnDoNPiAwgo0wIEBLYXhKB-14JOmBHP3JT7JltxldQZmaZYnVGGFltN8bQACymq_NkyHmbZ0_LEUUoDBCleszacHpfhZVkr7Q1GrgQFo0wUAKbR2yHIeW-6HysF7kFYSJTvCHOrgac2qj2lVpeKgdAvIZNTrgrLmZR1lBaOIw6TjDFtHExxZtZpi3_HUcRoZSD4smXi6TvdTGUXTLVDaEqMwDkFe6oxY="
client = TelegramClient(StringSession(session_str), api_id, api_hash)

# ------------------ утиліти -------------------------------------------------
def contains_keyword(text: str) -> bool:
    return any(k in text for k in KEYWORDS)

def translate_uk_to_ru(text: str) -> str:
    try:
        # Розбиваємо текст на шматки — валютні пари і решта
        tokens = re.split(r'(\b[A-Z]{3}\s?[\/]?\s?[A-Z]{3}\b)', text)

        translated_tokens = []
        for token in tokens:
            if re.fullmatch(r'\b[A-Z]{3}\s?[\/]?\s?[A-Z]{3}\b', token):
                # Це валютна пара — не перекладаємо
                translated_tokens.append(token)
            else:
                # Звичайний текст — перекладаємо
                if token.strip():
                    translated = translator.translate_text(token, source_lang='UK', target_lang='RU').text
                    translated_tokens.append(translated)
                else:
                    translated_tokens.append(token)

        return ''.join(translated_tokens)
    except Exception as e:
        print("🛑 Translate error:", e)
        return text


def clean(text: str) -> str:
    for p in BLOCK_PHRASES:
        text = text.replace(p, '')

    replacements = {
        'хвилина': 'минута',
        'хвилини': 'минуты',
        'хвилин': 'минут',
        'минуту': 'минуты',
        'верх': 'вверх',
        'Верх': 'вверх',
        'ВЕРХ': '(ВВЕРХ)',
        'догон': 'догон',
        'волатильність': 'волатильность',
        'дохідність': 'доходность',
        'торгову сесію': 'торговую сессию',
        'менеджмент': 'менеджмент'
    }

    for src, dst in replacements.items():
        text = text.replace(src, dst)

    return text.strip()

def save_map():
    MAP_FILE.write_text(json.dumps(msg_map))

def reformat_signal(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return text

    first = lines[0].upper()
    if "LONG" not in first and "SHORT" not in first:
        return text

    side = "LONG" if "LONG" in first else "SHORT"
    ticker = None
    for l in lines:
        if "монета" in l.lower():
            _, _, t = l.partition(":")
            ticker = t.strip().upper()
            break
        for token in l.replace(",", " ").split():
            if "/" in token and len(token) <= 15:
                ticker = token.upper().strip(":")
                break
        if ticker:
            break
    ticker = ticker or "???/???"
    if ticker == "???/???":
        ticker = lines[0].split()[0].upper()

    entry    = next((l for l in lines if "точка" in l.lower()), "")
    stop     = next((l for l in lines if "стоп"  in l.lower()), "")
    take     = next((l for l in lines if l.lower().startswith("take")), "")
    leverage = next((l for l in lines if "плеч" in l.lower()), "")

    out = [
        f"{ticker} ({side})",
        "",
        entry, stop, take,
        "",
        leverage
    ]
    return "\n".join(l for l in out if l.strip())

# ------------------- main ---------------------------------------------------
async def resolve_private(link: str) -> InputPeerChannel:
    res = await client(GetChannelsRequest(id=[link]))
    ch  = res.chats[0]
    return InputPeerChannel(ch.id, ch.access_hash)


async def main():
    global SOURCE_CHANNEL

    await client.start()
    TARGET_CHANNEL = await resolve_private('https://t.me/+8ABxxE4kkQtlNDEy')
    print("🔗 TARGET resolved:", TARGET_CHANNEL.channel_id)
    SOURCE_CHANNEL = await resolve_private('https://t.me/+AKsRB-gDtaRiOGRi')
    print("🔗 SOURCE resolved:", SOURCE_CHANNEL.channel_id)

    @client.on(events.NewMessage(chats=SOURCE_CHANNEL))
    async def forward_all(ev):
        msg = ev.message
    
        # 🔧 Пропускаємо голосові та кружки (round video)
        if getattr(msg, 'voice', None) or getattr(msg, 'video_note', None):
            return
    
        txt_uk = msg.message or ""
        txt_ru = translate_uk_to_ru(txt_uk)
        cleaned = reformat_signal(clean(txt_ru))
    
        # 🔁 Обробка відповіді
        reply_to = None
        if msg.is_reply:
            try:
                reply = await msg.get_reply_message()
                if reply:
                    reply_to = msg_map.get(str(reply.id))
            except Exception as e:
                print("🛑 Не вдалося обробити reply:", e)

        # 📤 Відправка
        if msg.media:
            sent = await client.send_file(
                TARGET_CHANNEL,
                file=msg.media,
                caption=cleaned or None,
                reply_to=reply_to
            )
        else:
            sent = await client.send_message(
                TARGET_CHANNEL,
                cleaned,
                reply_to=reply_to
            )
    
        msg_map[str(msg.id)] = sent.id
        save_map()

    @client.on(events.MessageEdited(chats=SOURCE_CHANNEL))
    async def sync_edit(ev):
        msg = ev.message
    
        # 🔧 Пропускаємо голосові та кружечки
        if getattr(msg, 'voice', None) or getattr(msg, 'video_note', None):
            return
    
        sid = str(msg.id)
        if sid not in msg_map:
            return
    
        txt_uk = msg.message or ""
        txt_ru = translate_uk_to_ru(txt_uk)
        cleaned = reformat_signal(clean(txt_ru))
        if not cleaned:
            return
    
        try:
            await client.edit_message(TARGET_CHANNEL, msg_map[sid], cleaned)
        except MessageNotModifiedError:
            pass
        except Exception as e:
            print("sync_edit error:", e)

    print("✅ Бот запущено")
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())
