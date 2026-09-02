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
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID") # Hoş geldin/Ayrılma kanalı ID'si (Opsiyonel)

# Uyarı verilerini hafızada tutmak için sözlük {guild_id: {user_id: count}}
warnings_data = {}

# ----------------------------------------------------------
# 1) BOT AYARLARI
# ----------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ----------------------------------------------------------
# SADECE ADMİNLER KULLANABİLİR (Tüm komutlar için)
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
# HOŞ GELDİN & AYRILMA ETKİNLİKLERİ
# ----------------------------------------------------------
def get_welcome_channel(guild):
    if WELCOME_CHANNEL_ID:
        channel = guild.get_channel(int(WELCOME_CHANNEL_ID))
        if channel:
            return channel
    return guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)

@bot.event
async def on_member_join(member):
    channel = get_welcome_channel(member.guild)
    if channel:
        await channel.send(f"👋 Hoş geldin {member.mention}! Sunucumuza katıldığın için mutluyuz.")

@bot.event
async def on_member_remove(member):
    channel = get_welcome_channel(member.guild)
    if channel:
        await channel.send(f"📤 **{member}** sunucumuzdan ayrıldı.")


# ----------------------------------------------------------
# 2) SESLİ KANALDA 7/24 AFK BEKLEME
# ----------------------------------------------------------
async def join_afk_channel():
    if not VOICE_CHANNEL_ID:
        return

    channel = bot.get_channel(int(VOICE_CHANNEL_ID))
    if channel is None:
        print("⚠️ VOICE_CHANNEL_ID hatalı, böyle bir ses kanalı bulunamadı.")
        return

    if channel.guild.voice_client is not None:
        return

    try:
        await channel.connect(self_deaf=True, self_mute=True)
        print(f'🔊 "{channel.name}" ses kanalına girildi, 7/24 orada bekleyecek.')
    except Exception as e:
        print(f"⚠️ Ses kanalına bağlanırken hata oluştu: {e}")


@tasks.loop(seconds=30)
async def voice_watchdog():
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
# 4) YARDIMCI FONKSİYONLAR
# ----------------------------------------------------------
async def get_mentioned_member(ctx):
    if ctx.message.mentions:
        return ctx.message.mentions[0]
    return None

async def get_mentioned_role(ctx):
    if ctx.message.role_mentions:
        return ctx.message.role_mentions[0]
    return None


# ----------------------------------------------------------
# 5) KOMUTLAR
# ----------------------------------------------------------

@bot.command(name="yardım", aliases=["yardim", "help"])
async def yardim(ctx):
    mesaj = (
        f"🛠️ **Moderasyon Komutları**\n"
        f"• `{PREFIX}sil <sayı>` — Belirtilen sayıda mesajı siler\n"
        f"• `{PREFIX}ban @üye [sebep]` — Üyeyi banlar\n"
        f"• `{PREFIX}unban <ID>` — Üyenin banını kaldırır\n"
        f"• `{PREFIX}kick @üye [sebep]` — Üyeyi sunucudan atar\n"
        f"• `{PREFIX}timeout @üye <dakika> [sebep]` — Üyeyi susturur\n"
        f"• `{PREFIX}unmute @üye` — Timeout'u erken kaldırır\n"
        f"• `{PREFIX}warn @üye [sebep]` — Uyarı verir (3 uyarıda otomatik 10dk mute)\n"
        f"• `{PREFIX}warnings @üye` — Üyenin uyarı sayısını gösterir\n"
        f"• `{PREFIX}lock` / `{PREFIX}unlock` — Kanalı kilitler/açar\n"
        f"• `{PREFIX}slowmode <saniye>` — Kanala yavaş mod uygular\n\n"
        f"👑 **Sunucu Yönetimi**\n"
        f"• `{PREFIX}nick @üye <yeni isim>` — Takma isim değiştirir\n"
        f"• `{PREFIX}rolver @üye @rol` / `{PREFIX}rolal @üye @rol` — Rol verir/alır\n\n"
        f"🎮 **Eğlence / Ekstra**\n"
        f"• `{PREFIX}avatar [@üye]` — Profil fotoğrafını gösterir\n"
        f"• `{PREFIX}userinfo [@üye]` — Üye bilgisini gösterir\n"
        f"• `{PREFIX}serverinfo` — Sunucu istatistiklerini gösterir\n"
        f"• `{PREFIX}ping` — Botun gecikme süresini gösterir"
    )
    await ctx.reply(mesaj)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Gecikme: **{round(bot.latency * 1000)}ms**")


# --- MODERASYON & TEMİZLİK ---

@bot.command(name="sil", aliases=["mesajsil", "clear", "purge"])
async def sil(ctx, miktar: str = None):
    if miktar is None or not miktar.isdigit():
        await ctx.reply(f"⚠️ Lütfen mesaj miktarını yazın! Örnek: `{PREFIX}sil 50`")
        return

    miktar = int(miktar)
    if miktar < 1 or miktar > 1000:
        await ctx.reply("⚠️ Lütfen 1 ile 1000 arasında bir sayı girin!")
        return

    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.reply("❌ Bu kanalda mesajları yönetme yetkim yok!")
        return

    try:
        silinenler = await ctx.channel.purge(limit=miktar + 1)
        toplam_silinen = len(silinenler) - 1
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


@bot.command(name="unmute", aliases=["untimeout"])
async def unmute(ctx, uye: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen susturması kaldırılacak üyeyi etiketleyin! Örnek: `{PREFIX}unmute @üye`")
        return

    try:
        await member.timeout(None)
        await ctx.send(f"🔊 **{member}** üzerindeki susturma (timeout) kaldırıldı.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Susturma kaldırılırken bir hata oluştu.")


# --- UYARI SİSTEMİ ---

@bot.command(name="warn", aliases=["uyar"])
async def warn(ctx, uye: str = None, *, sebep: str = "Sebep belirtilmedi"):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen uyarmak istediğiniz üyeyi etiketleyin! Örnek: `{PREFIX}warn @üye [sebep]`")
        return

    guild_id = ctx.guild.id
    user_id = member.id

    if guild_id not in warnings_data:
        warnings_data[guild_id] = {}
    
    warnings_data[guild_id][user_id] = warnings_data[guild_id].get(user_id, 0) + 1
    toplam_uyari = warnings_data[guild_id][user_id]

    await ctx.send(f"⚠️ **{member.mention}** uyarıldı! (Toplam Uyarı: **{toplam_uyari}**)\n📝 Sebep: {sebep}")

    # 3. Uyarıda Otomatik Mute (10 Dakika Timeout)
    if toplam_uyari >= 3:
        sure = discord.utils.utcnow() + discord.utils.timedelta(minutes=10)
        try:
            await member.timeout(sure, reason="3 Uyarı sınırına ulaşıldı.")
            await ctx.send(f"🚫 **{member.mention}** 3 uyarı aldığı için otomatik olarak **10 dakika** susturuldu!")
            warnings_data[guild_id][user_id] = 0  # Sayacı sıfırla
        except Exception as e:
            print(f"Otomatik mute hatası: {e}")


@bot.command(name="warnings", aliases=["uyarılar", "uyarilar"])
async def warnings(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    guild_id = ctx.guild.id
    user_id = member.id

    sayi = warnings_data.get(guild_id, {}).get(user_id, 0)
    await ctx.reply(f"📊 **{member.display_name}** adlı kullanıcının mevcut uyarı sayısı: **{sayi}**")


# --- KANAL YÖNETİMİ ---

@bot.command(name="lock", aliases=["kilitle"])
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Kanal kilitlendi. Artık kimse mesaj gönderemez.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Kanal kilitlenirken bir hata oluştu.")


@bot.command(name="unlock", aliases=["kilitac", "kilit-ac"])
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Kanalın kilidi açıldı. Artık mesaj gönderilebilir.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Kanal kilidi açılırken bir hata oluştu.")


@bot.command(name="slowmode", aliases=["yavasmod", "yavaşmod"])
async def slowmode(ctx, saniye: str = None):
    if saniye is None or not saniye.isdigit():
        await ctx.reply(f"⚠️ Lütfen saniye cinsinden bir değer girin! Örnek: `{PREFIX}slowmode 5` (Kapatmak için `0`)")
        return

    sec = int(saniye)
    try:
        await ctx.channel.edit(slowmode_delay=sec)
        if sec == 0:
            await ctx.send("⏱️ Kanalın yavaş modu kapatıldı.")
        else:
            await ctx.send(f"⏱️ Kanalın yavaş modu **{sec} saniye** olarak ayarlandı.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Yavaş mod ayarlanırken bir hata oluştu.")


# --- SUNUCU / ÜYE YÖNETİMİ ---

@bot.command(name="nick", aliases=["isim", "takmaisim"])
async def nick(ctx, uye: str = None, *, yeni_isim: str = None):
    member = await get_mentioned_member(ctx)
    if member is None or yeni_isim is None:
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}nick @üye yeni isim`")
        return

    try:
        await member.edit(nick=yeni_isim)
        await ctx.send(f"✅ **{member.name}** kullanıcısının ismi **{yeni_isim}** olarak değiştirildi.")
    except Exception as e:
        print(e)
        await ctx.send("❌ İsim değiştirilemedi (Yetkim yetersiz olabilir).")


@bot.command(name="rolver", aliases=["addrole"])
async def rolver(ctx, uye: str = None, rol: str = None):
    member = await get_mentioned_member(ctx)
    role = await get_mentioned_role(ctx)

    if member is None or role is None:
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}rolver @üye @rol`")
        return

    try:
        await member.add_roles(role)
        await ctx.send(f"✅ **{member.display_name}** kullanıcısına **{role.name}** rolü verildi.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Rol verilemedi (Yetkim rolün altında olabilir).")


@bot.command(name="rolal", aliases=["removerole"])
async def rolal(ctx, uye: str = None, rol: str = None):
    member = await get_mentioned_member(ctx)
    role = await get_mentioned_role(ctx)

    if member is None or role is None:
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}rolal @üye @rol`")
        return

    try:
        await member.remove_roles(role)
        await ctx.send(f"✅ **{member.display_name}** kullanıcısından **{role.name}** rolü alındı.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Rol alınamadı (Yetkim rolün altında olabilir).")


# --- EĞLENCE & BİLGİ ---

@bot.command(name="avatar", aliases=["pp"])
async def avatar(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    embed = discord.Embed(title=f"🖼️ {member.display_name} Profil Fotoğrafı", color=discord.Color.blue())
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="userinfo", aliases=["kullanıcıbilgi", "kullanicibilgi"])
async def userinfo(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    roller = [r.mention for r in member.roles[1:]] or ["Yok"]

    embed = discord.Embed(title=f"👤 {member}", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🆔 Kullanıcı ID", value=member.id, inline=True)
    embed.add_field(name="📅 Katılma Tarihi", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="🚀 Hesap Oluşturma", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name=f"🎭 Roller [{len(roller)}]", value=", ".join(roller), inline=False)
    
    await ctx.send(embed=embed)


@bot.command(name="serverinfo", aliases=["sunucubilgi"])
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"🏰 {guild.name} Sunucu Bilgileri", color=discord.Color.purple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="👑 Sunucu Sahibi", value=guild.owner.mention, inline=True)
    embed.add_field(name="🆔 Sunucu ID", value=guild.id, inline=True)
    embed.add_field(name="👥 Üye Sayısı", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Metin Kanalları", value=len(guild.text_channels), inline=True)
    embed.add_field(name="🔊 Ses Kanalları", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="📅 Oluşturulma Tarihi", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)

    await ctx.send(embed=embed)


# ----------------------------------------------------------
# 6) RENDER İÇİN KEEP-ALIVE (WEB SERVICE + SELF-PING)
# ----------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def anasayfa():
    return "TheCanada Bot çalışıyor ✅"


def flask_calistir():
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)


def self_ping():
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        print("ℹ️ RENDER_EXTERNAL_URL bulunamadı, self-ping devre dışı (lokal ortamda normaldir).")
        return

    while True:
        time.sleep(4 * 60)
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
