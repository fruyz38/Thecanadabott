# ==========================================================
#  TheCanada Bot - Moderasyon Botu (c! prefix) - Python sürümü
#  discord.py ile yazılmıştır, Render Web Service için hazırdır.
# ==========================================================

import os
import asyncio
import threading
import time

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from flask import Flask
import requests

load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX", "c!")
VOICE_CHANNEL_ID = os.getenv("VOICE_CHANNEL_ID")

# ----------------------------------------------------------
# 1) BOT AYARLARI
# ----------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ----------------------------------------------------------
# SADECE ADMİNLER KULLANABİLİR
# Bu kontrol her komuttan önce otomatik çalışır, DM'lerde
# ve yönetici olmayan üyelerde komutlar çalışmaz.
# ----------------------------------------------------------
@bot.check
async def sadece_adminler(ctx):
    if ctx.guild is None:
        return False  # DM'lerde çalışmasın
    if ctx.author.guild_permissions.administrator:
        return True
    raise commands.CheckFailure("no_admin")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ Bu botu sadece **yöneticiler (Administrator)** kullanabilir!")
        return
    if isinstance(error, commands.CommandNotFound):
        return  # Bilinmeyen komutlarda sessiz kal
    print(f"Beklenmeyen hata: {error}")


# ----------------------------------------------------------
# 2) SESLİ KANALDA 7/24 AFK BEKLEME
# ----------------------------------------------------------
async def join_afk_channel():
    if not VOICE_CHANNEL_ID:
        return  # Ses kanalı belirtilmediyse bu özelliği atla

    channel = bot.get_channel(int(VOICE_CHANNEL_ID))
    if channel is None:
        print("⚠️ VOICE_CHANNEL_ID hatalı, böyle bir ses kanalı bulunamadı.")
        return

    # Zaten bağlıysa tekrar bağlanmaya çalışma
    if channel.guild.voice_client is not None:
        return

    try:
        await channel.connect(self_deaf=True, self_mute=True)
        print(f'🔊 "{channel.name}" ses kanalına girildi, 7/24 orada bekleyecek.')
    except Exception as e:
        print(f"⚠️ Ses kanalına bağlanırken hata oluştu: {e}")


@tasks.loop(seconds=30)
async def voice_watchdog():
    """Bot ses kanalından koparsa otomatik olarak tekrar bağlanır."""
    if not VOICE_CHANNEL_ID:
        return
    for guild in bot.guilds:
        if guild.voice_client is None or not guild.voice_client.is_connected():
            await join_afk_channel()


# ----------------------------------------------------------
# 3) BOT HAZIR OLDUĞUNDA
# ----------------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ {bot.user} olarak giriş yapıldı!")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}yardım")
    )
    await join_afk_channel()
    if not voice_watchdog.is_running():
        voice_watchdog.start()


# ----------------------------------------------------------
# 4) YARDIMCI FONKSİYON: ETİKETLENEN ÜYEYİ BULMA
# ----------------------------------------------------------
async def get_mentioned_member(ctx):
    if ctx.message.mentions:
        return ctx.message.mentions[0]
    return None


# ----------------------------------------------------------
# 5) KOMUTLAR
# ----------------------------------------------------------

@bot.command(name="yardım", aliases=["yardim", "help"])
async def yardim(ctx):
    mesaj = (
        f"**{PREFIX}sil <sayı>** — Belirtilen sayıda mesajı siler (örn: `{PREFIX}sil 50`)\n"
        f"**{PREFIX}ban @üye [sebep]** — Üyeyi sunucudan banlar\n"
        f"**{PREFIX}unban <kullanıcı ID>** — Üyenin banını kaldırır\n"
        f"**{PREFIX}kick @üye [sebep]** — Üyeyi sunucudan atar\n"
        f"**{PREFIX}timeout @üye <dakika> [sebep]** — Üyeyi belirtilen süre susturur\n"
        f"**{PREFIX}ping** — Botun gecikme süresini gösterir"
    )
    await ctx.reply(mesaj)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Gecikme: **{round(bot.latency * 1000)}ms**")


@bot.command(name="sil", aliases=["mesajsil", "clear", "purge"])
async def sil(ctx, miktar: str = None):
    if miktar is None:
        await ctx.reply(f"⚠️ Lütfen mesaj miktarını yazın! Örnek: `{PREFIX}sil 50`")
        return

    if not miktar.isdigit():
        await ctx.reply(f"⚠️ Lütfen mesaj miktarını yazın! Örnek: `{PREFIX}sil 50`")
        return

    miktar = int(miktar)
    if miktar < 1 or miktar > 1000:
        await ctx.reply("⚠️ Lütfen 1 ile 1000 arasında bir sayı girin!")
        return

    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.reply("❌ Bu kanalda mesajları yönetme yetkim yok, rollerimi kontrol et!")
        return

    try:
        # Komut mesajı dahil miktar+1 mesaj siliniyor (kendi komutunu da temizler)
        silinenler = await ctx.channel.purge(limit=miktar + 1)
        toplam_silinen = len(silinenler) - 1  # komut mesajını sayma
        bilgi = await ctx.send(f"✅ **{max(toplam_silinen, 0)}** mesaj başarıyla silindi.")
        await asyncio.sleep(5)
        await bilgi.delete()
    except Exception as e:
        print(e)
        await ctx.send("❌ Mesajlar silinirken bir hata oluştu.")


@bot.command(name="ban")
async def ban(ctx, *, arg: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen banlamak istediğiniz üyeyi etiketleyin! Örnek: `{PREFIX}ban @üye sebep`")
        return

    if member.top_role >= ctx.guild.me.top_role or member == ctx.guild.owner:
        await ctx.reply("❌ Bu üyeyi banlayamıyorum (rolüm yeterince yüksek olmayabilir).")
        return

    # "@üye sebep" formatındaki metinden sebebi ayıkla
    reason = "Sebep belirtilmedi"
    if arg:
        parcalar = arg.split(maxsplit=1)
        if len(parcalar) > 1:
            reason = parcalar[1]

    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ **{member}** sunucudan banlandı.\n📝 Sebep: {reason}")
    except Exception as e:
        print(e)
        await ctx.send("❌ Üye banlanırken bir hata oluştu.")


@bot.command(name="unban")
async def unban(ctx, user_id: str = None):
    if user_id is None or not user_id.isdigit():
        await ctx.reply(f"⚠️ Lütfen banı kaldırılacak kullanıcının ID'sini yazın! Örnek: `{PREFIX}unban 123456789012345678`")
        return

    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"✅ Kullanıcının (ID: {user_id}) banı kaldırıldı.")
    except Exception:
        await ctx.reply("❌ Bu ID ile banlı bir kullanıcı bulunamadı.")


@bot.command(name="kick")
async def kick(ctx, *, arg: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen atmak istediğiniz üyeyi etiketleyin! Örnek: `{PREFIX}kick @üye sebep`")
        return

    if member.top_role >= ctx.guild.me.top_role or member == ctx.guild.owner:
        await ctx.reply("❌ Bu üyeyi atamıyorum (rolüm yeterince yüksek olmayabilir).")
        return

    reason = "Sebep belirtilmedi"
    if arg:
        parcalar = arg.split(maxsplit=1)
        if len(parcalar) > 1:
            reason = parcalar[1]

    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ **{member}** sunucudan atıldı.\n📝 Sebep: {reason}")
    except Exception as e:
        print(e)
        await ctx.send("❌ Üye atılırken bir hata oluştu.")


@bot.command(name="timeout", aliases=["sustur"])
async def timeout(ctx, uye: str = None, dakika: str = None, *, sebep: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen susturmak istediğiniz üyeyi etiketleyin! Örnek: `{PREFIX}timeout @üye 10 sebep`")
        return

    if dakika is None or not dakika.isdigit():
        await ctx.reply(f"⚠️ Lütfen süreyi dakika olarak yazın! Örnek: `{PREFIX}timeout @üye 10 sebep`")
        return

    reason = sebep or "Sebep belirtilmedi"
    sure = discord.utils.utcnow() + discord.utils.timedelta(minutes=int(dakika))

    try:
        await member.timeout(sure, reason=reason)
        await ctx.send(f"✅ **{member}** {dakika} dakika susturuldu.\n📝 Sebep: {reason}")
    except Exception as e:
        print(e)
        await ctx.send("❌ Üye susturulurken bir hata oluştu.")


# ----------------------------------------------------------
# 6) RENDER İÇİN KEEP-ALIVE (WEB SERVICE + SELF-PING)
#    Render'ın ücretsiz Web Service'i belli bir süre trafik
#    almazsa uykuya geçer. Aşağıdaki Flask sunucusu ve
#    kendi kendine ping atma sistemi bunu engeller.
# ----------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def anasayfa():
    return "TheCanada Bot çalışıyor ✅"


def flask_calistir():
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)


def self_ping():
    """Botun kendi kendine periyodik olarak ping atmasını sağlar.
    RENDER_EXTERNAL_URL değeri Render tarafından otomatik olarak
    ortam değişkeni (environment variable) olarak sağlanır."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        print("ℹ️ RENDER_EXTERNAL_URL bulunamadı, self-ping devre dışı (lokal ortamda normaldir).")
        return

    while True:
        time.sleep(4 * 60)  # Her 4 dakikada bir
        try:
            requests.get(url, timeout=10)
            print("🔄 Self-ping gönderildi, bot uyanık tutuluyor.")
        except Exception as e:
            print(f"⚠️ Self-ping başarısız oldu: {e}")


def keep_alive():
    threading.Thread(target=flask_calistir, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()


# ----------------------------------------------------------
# 7) BOTU BAŞLAT
# ----------------------------------------------------------
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)