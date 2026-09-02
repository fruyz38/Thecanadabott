# ==========================================================
#  TheCanada Bot - Moderasyon & Eğlence Botu (c! prefix)
#  discord.py ile yazılmıştır, Render Web Service için hazırdır.
# ==========================================================

import os
import asyncio
import threading
import time
import random

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from flask import Flask
import requests

load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = os.getenv("PREFIX", "c!")
VOICE_CHANNEL_ID = os.getenv("VOICE_CHANNEL_ID")
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")

# Hafıza Verileri
warnings_data = {} # {guild_id: {user_id: count}}
afk_users = {}     # {guild_id: {user_id: {"reason": str, "old_nick": str}}}
active_games = {}  # {channel_id: {"type": "sayitahmin", "number": int, "attempts": int}}

# ----------------------------------------------------------
# 1) BOT AYARLARI
# ----------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ----------------------------------------------------------
# YETKİ KONTROLÜ (Eğlence ve Genel Komutlar Herkese Açık)
# ----------------------------------------------------------
@bot.check
async def yetki_kontrolu(ctx):
    if ctx.guild is None:
        return False
    
    # Herkesin kullanabileceği komut listesi
    herkese_acik = [
        "afk", "yardım", "yardim", "help", "ping", "avatar", "pp", 
        "userinfo", "kullanıcıbilgi", "kullanicibilgi", "serverinfo", "sunucubilgi",
        "8ball", "zar", "yazitura", "yazıtura", "duello", "düello", "sayitahmin", "sayıtahmin",
        "saril", "sarıl", "tokat"
    ]
    
    if ctx.command and ctx.command.name in herkese_acik:
        return True
    
    if ctx.author.guild_permissions.administrator:
        return True
    raise commands.CheckFailure("no_admin")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ Bu moderasyon komutunu sadece **yöneticiler (Administrator)** kullanabilir!")
        return
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Beklenmeyen hata: {error}")


# ----------------------------------------------------------
# AFK VE SAYI TAHMİN OYUNU DİNLEYİCİSİ (ON_MESSAGE)
# ----------------------------------------------------------
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    guild_id = message.guild.id
    user_id = message.author.id
    channel_id = message.channel.id

    # 1. AFK KONTROLÜ
    if guild_id in afk_users and user_id in afk_users[guild_id]:
        data = afk_users[guild_id].pop(user_id)
        old_nick = data.get("old_nick")
        
        try:
            await message.author.edit(nick=old_nick)
        except Exception:
            pass

        await message.channel.send(f"👋 **{message.author.display_name}**, tekrar hoş geldin! AFK modundan çıkarıldın.", delete_after=5)

    if message.mentions:
        for mentioned_user in message.mentions:
            if guild_id in afk_users and mentioned_user.id in afk_users[guild_id]:
                reason = afk_users[guild_id][mentioned_user.id]["reason"]
                await message.reply(f"💤 **{mentioned_user.display_name}** şu anda AFK!\n📝 **Sebep:** {reason}")

    # 2. SAYI TAHMİN OYUNU KONTROLÜ
    if channel_id in active_games and active_games[channel_id]["type"] == "sayitahmin":
        if message.content.isdigit():
            tahmin = int(message.content)
            hedef = active_games[channel_id]["number"]
            active_games[channel_id]["attempts"] += 1

            if tahmin < hedef:
                await message.add_reaction("⬆️")
            elif tahmin > hedef:
                await message.add_reaction("⬇️")
            else:
                deneme = active_games[channel_id]["attempts"]
                del active_games[channel_id]
                await message.reply(f"🎉 **TEBRİKLER!** Doğru sayıyı bildin: **{hedef}**\n📊 Toplam **{deneme}** tahminde bulundu.")

    await bot.process_commands(message)


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
# SESLİ KANALDA 7/24 AFK BEKLEME
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
# YARDIMCI FONKSİYONLAR
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
# KOMUTLAR
# ----------------------------------------------------------

@bot.command(name="yardım", aliases=["yardim", "help"])
async def yardim(ctx):
    mesaj = (
        f"🎮 **Eğlence & Oyun Komutları**\n"
        f"• `{PREFIX}sayitahmin` — 1-100 arası sayı tahmin oyununu başlatır\n"
        f"• `{PREFIX}duello @üye` — Belirtilen üye ile 1v1 kapışma başlatır\n"
        f"• `{PREFIX}8ball <soru>` — Mistik küre sorunu yanıtlar\n"
        f"• `{PREFIX}zar` — 1-6 arası zar atar\n"
        f"• `{PREFIX}yazitura` — Yazı mı tura mı atar\n"
        f"• `{PREFIX}saril @üye` / `{PREFIX}tokat @üye` — Eğlenceli etkileşimler\n"
        f"• `{PREFIX}afk [sebep]` — AFK moduna geçer\n\n"
        f"🛠️ **Moderasyon (Sadece Admin)**\n"
        f"• `{PREFIX}sil <sayı>` | `{PREFIX}ban` | `{PREFIX}kick` | `{PREFIX}timeout` | `{PREFIX}unmute`\n"
        f"• `{PREFIX}warn` | `{PREFIX}warnings` | `{PREFIX}lock` | `{PREFIX}unlock` | `{PREFIX}slowmode`\n"
        f"• `{PREFIX}nick` | `{PREFIX}rolver` | `{PREFIX}rolal`"
    )
    await ctx.reply(mesaj)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Gecikme: **{round(bot.latency * 1000)}ms**")


# --- OYUN & EĞLENCE KOMUTLARI ---

@bot.command(name="sayitahmin", aliases=["sayıtahmin"])
async def sayitahmin(ctx):
    channel_id = ctx.channel.id
    if channel_id in active_games:
        await ctx.reply("⚠️ Bu kanalda zaten aktif bir oyun var!")
        return

    gizli_sayi = random.randint(1, 100)
    active_games[channel_id] = {
        "type": "sayitahmin",
        "number": gizli_sayi,
        "attempts": 0
    }

    await ctx.send("🎲 **Sayı Tahmin Oyunu Başladı!**\n1 ile 100 arasında bir sayı tuttum. Tahminlerinizi doğrudan kanala yazın! (Daha büyük için ⬆️, daha küçük için ⬇️ tepkisi vereceğim)")


@bot.command(name="duello", aliases=["düello"])
async def duello(ctx):
    rakip = await get_mentioned_member(ctx)
    if rakip is None or rakip == ctx.author or rakip.bot:
        await ctx.reply("⚠️ Lütfen kapışmak için geçerli bir üye etiketleyin!")
        return

    mesaj = await ctx.send(f"⚔️ {ctx.author.mention} vs {rakip.mention}\nDüello başlıyor... Kılıçlar çekildi! 🗡️")
    await asyncio.sleep(2)

    sira = [ctx.author, rakip]
    random.shuffle(sira)
    kazanan = sira[0]
    kaybeden = sira[1]

    vurus_stilleri = [
        f"efsanevi bir kritik vuruşla {kaybeden.mention} kullanıcısını nakavt etti!",
        f"kalkanıyla {kaybeden.mention} kullanıcısını yere serdi!",
        f"son hamlesiyle {kaybeden.mention} kullanıcısını mağlup etti!"
    ]

    await mesaj.edit(content=f"⚔️ **DÜELLO BİTTİ!**\n🏆 **Kazanan:** {kazanan.mention}\n🔥 {kazanan.mention}, {random.choice(vurus_stilleri)}")


@bot.command(name="8ball")
async def eight_ball(ctx, *, soru: str = None):
    if soru is None:
        await ctx.reply(f"⚠️ Lütfen bota bir soru sor! Örnek: `{PREFIX}8ball Bugün şanslı mıyım?`")
        return

    cevaplar = [
        "Kesinlikle evet! ✨",
        "Şüphesiz öyle. 👍",
        "Büyük ihtimalle... 🤔",
        "Pek sanmıyorum. 🛑",
        "İmkansız, unut bunu! ❌",
        "Zaman gösterir, şu an cevap veremem. 🔮",
        "Kaderin bu soruya kapalı. 🌫️",
        "Yüzde yüz! 🔥"
    ]
    await ctx.reply(f"🔮 **Soru:** {soru}\n🎱 **Cevap:** {random.choice(cevaplar)}")


@bot.command(name="zar")
async def zar(ctx):
    sonuc = random.randint(1, 6)
    await ctx.reply(f"🎲 Zarı attın ve **{sonuc}** geldi!")


@bot.command(name="yazitura", aliases=["yazıtura"])
async def yazitura(ctx):
    sonuc = random.choice(["Yazı 🪙", "Tura 🦅"])
    await ctx.reply(f"🪙 Para havaya atıldı... **{sonuc}**!")


@bot.command(name="saril", aliases=["sarıl"])
async def saril(ctx):
    hedef = await get_mentioned_member(ctx)
    if hedef is None or hedef == ctx.author:
        await ctx.reply("⚠️ Lütfen sarılmak istediğin birini etiketle!")
        return

    gifler = [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExdW5pczE0a3B5Z29pZ3IxeHFueWtyc3dwbXB2aXdpZHdveWZzNTUycCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3M4NpbLCTxBqU/giphy.gif",
        "https://media.giphy.com/media/l2QDM9Jnim1YV55YA/giphy.gif"
    ]
    embed = discord.Embed(
        description=f"🤗 {ctx.author.mention}, {hedef.mention} kişisine sımsıkı sarıldı!",
        color=discord.Color.purple()
    )
    embed.set_image(url=random.choice(gifler))
    await ctx.send(embed=embed)


@bot.command(name="tokat")
async def tokat(ctx):
    hedef = await get_mentioned_member(ctx)
    if hedef is None or hedef == ctx.author:
        await ctx.reply("⚠️ Lütfen tokatlamak istediğin birini etiketle!")
        return

    gifler = [
        "https://media.giphy.com/media/Gf3AUz3eBNbTW/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbTZ5NW1ocmR5MXQxcXZmdXZpMXp6M2IxdnVrcTVwMXRrc2JndHFtZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/j3iGKfXRKlLqw/giphy.gif"
    ]
    embed = discord.Embed(
        description=f"💥 {ctx.author.mention}, {hedef.mention} kişisine osmanlı tokadı yapıştırdı!",
        color=discord.Color.red()
    )
    embed.set_image(url=random.choice(gifler))
    await ctx.send(embed=embed)


@bot.command(name="afk")
async def afk(ctx, *, sebep: str = "Sebep belirtilmedi"):
    guild_id = ctx.guild.id
    user_id = ctx.author.id

    if guild_id not in afk_users:
        afk_users[guild_id] = {}

    old_nick = ctx.author.display_name
    afk_users[guild_id][user_id] = {
        "reason": sebep,
        "old_nick": ctx.author.nick
    }

    try:
        new_nick = f"[AFK] {old_nick}"[:32]
        await ctx.author.edit(nick=new_nick)
    except Exception:
        pass

    await ctx.send(f"💤 {ctx.author.mention} artık **AFK**.\n📝 **Sebep:** {sebep}")


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
        await ctx.reply(f"⚠️ Lütfen banlamak istediğiniz üyeyi etiketleyin!")
        return

    if member.top_role >= ctx.guild.me.top_role or member == ctx.guild.owner:
        await ctx.reply("❌ Bu üyeyi banlayamıyorum.")
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


@bot.command(name="kick")
async def kick(ctx, *, arg: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen atmak istediğiniz üyeyi etiketleyin!")
        return

    if member.top_role >= ctx.guild.me.top_role or member == ctx.guild.owner:
        await ctx.reply("❌ Bu üyeyi atamıyorum.")
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
    if member is None or dakika is None or not dakika.isdigit():
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}timeout @üye 10 sebep`")
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
        await ctx.reply(f"⚠️ Lütfen susturması kaldırılacak üyeyi etiketleyin!")
        return

    try:
        await member.timeout(None)
        await ctx.send(f"🔊 **{member}** üzerindeki susturma kaldırıldı.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Susturma kaldırılırken bir hata oluştu.")


@bot.command(name="warn", aliases=["uyar"])
async def warn(ctx, uye: str = None, *, sebep: str = "Sebep belirtilmedi"):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply(f"⚠️ Lütfen uyarmak istediğiniz üyeyi etiketleyin!")
        return

    guild_id = ctx.guild.id
    user_id = member.id

    if guild_id not in warnings_data:
        warnings_data[guild_id] = {}
    
    warnings_data[guild_id][user_id] = warnings_data[guild_id].get(user_id, 0) + 1
    toplam_uyari = warnings_data[guild_id][user_id]

    await ctx.send(f"⚠️ **{member.mention}** uyarıldı! (Toplam Uyarı: **{toplam_uyari}**)\n📝 Sebep: {sebep}")

    if toplam_uyari >= 3:
        sure = discord.utils.utcnow() + discord.utils.timedelta(minutes=10)
        try:
            await member.timeout(sure, reason="3 Uyarı sınırına ulaşıldı.")
            await ctx.send(f"🚫 **{member.mention}** 3 uyarı aldığı için otomatik olarak **10 dakika** susturuldu!")
            warnings_data[guild_id][user_id] = 0
        except Exception as e:
            print(f"Otomatik mute hatası: {e}")


@bot.command(name="warnings", aliases=["uyarılar", "uyarilar"])
async def warnings(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    guild_id = ctx.guild.id
    user_id = member.id

    sayi = warnings_data.get(guild_id, {}).get(user_id, 0)
    await ctx.reply(f"📊 **{member.display_name}** adlı kullanıcının mevcut uyarı sayısı: **{sayi}**")


@bot.command(name="lock", aliases=["kilitle"])
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔒 Kanal kilitlendi.")
    except Exception as e:
        print(e)


@bot.command(name="unlock", aliases=["kilitac"])
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.send("🔓 Kanalın kilidi açıldı.")
    except Exception as e:
        print(e)


@bot.command(name="slowmode", aliases=["yavasmod"])
async def slowmode(ctx, saniye: str = None):
    if saniye is None or not saniye.isdigit():
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}slowmode 5` (Kapatmak için `0`)")
        return

    sec = int(saniye)
    try:
        await ctx.channel.edit(slowmode_delay=sec)
        await ctx.send(f"⏱️ Yavaş mod **{sec} saniye** olarak ayarlandı.")
    except Exception as e:
        print(e)


@bot.command(name="nick", aliases=["isim"])
async def nick(ctx, uye: str = None, *, yeni_isim: str = None):
    member = await get_mentioned_member(ctx)
    if member is None or yeni_isim is None:
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}nick @üye yeni isim`")
        return

    try:
        await member.edit(nick=yeni_isim)
        await ctx.send(f"✅ **{member.name}** ismi **{yeni_isim}** olarak değiştirildi.")
    except Exception as e:
        print(e)


@bot.command(name="rolver", aliases=["addrole"])
async def rolver(ctx, uye: str = None, rol: str = None):
    member = await get_mentioned_member(ctx)
    role = await get_mentioned_role(ctx)
    if member and role:
        await member.add_roles(role)
        await ctx.send(f"✅ **{member.display_name}** kullanıcısına **{role.name}** rolü verildi.")


@bot.command(name="rolal", aliases=["removerole"])
async def rolal(ctx, uye: str = None, rol: str = None):
    member = await get_mentioned_member(ctx)
    role = await get_mentioned_role(ctx)
    if member and role:
        await member.remove_roles(role)
        await ctx.send(f"✅ **{member.display_name}** kullanıcısından **{role.name}** rolü alındı.")


@bot.command(name="avatar", aliases=["pp"])
async def avatar(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    embed = discord.Embed(title=f"🖼️ {member.display_name} Profil Fotoğrafı", color=discord.Color.blue())
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="userinfo")
async def userinfo(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    roller = [r.mention for r in member.roles[1:]] or ["Yok"]

    embed = discord.Embed(title=f"👤 {member}", color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🆔 ID", value=member.id, inline=True)
    embed.add_field(name="📅 Katılma", value=member.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="🚀 Oluşturulma", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name=f"🎭 Roller [{len(roller)}]", value=", ".join(roller), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="serverinfo")
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"🏰 {guild.name} Sunucu Bilgileri", color=discord.Color.purple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👑 Sahibi", value=guild.owner.mention, inline=True)
    embed.add_field(name="👥 Üye Sayısı", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Metin Kanalları", value=len(guild.text_channels), inline=True)
    embed.add_field(name="🔊 Ses Kanalları", value=len(guild.voice_channels), inline=True)
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
        print("ℹ️ RENDER_EXTERNAL_URL bulunamadı, self-ping devre dışı.")
        return

    while True:
        time.sleep(4 * 60)
        try:
            requests.get(url, timeout=10)
            print("🔄 Self-ping gönderildi.")
        except Exception as e:
            print(f"⚠️ Self-ping hatası: {e}")


def keep_alive():
    threading.Thread(target=flask_calistir, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()


# ----------------------------------------------------------
# 7) BOTU BAŞLAT
# ----------------------------------------------------------
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
