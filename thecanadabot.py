# ==========================================================
#  TheCanada Bot - Moderasyon, Eğlence & Otomasyon Botu (c! prefix)
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

# Otomatik Duyuru Ayarları
auto_message_config = {
    "channel_id": None,
    "interval_minutes": 60,
    "message": None,
    "running": False
}

# ----------------------------------------------------------
# 1) BOT AYARLARI
# ----------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.presences = True  # Spotify etkinliği tespiti için ŞART

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ----------------------------------------------------------
# YETKİ KONTROLÜ
# ----------------------------------------------------------
@bot.check
async def yetki_kontrolu(ctx):
    if ctx.guild is None:
        return False
    
    # Herkesin kullanabileceği komutlar
    herkese_acik = [
        "afk", "yardım", "yardim", "help", "ping", "avatar", "pp", 
        "userinfo", "kullanıcıbilgi", "kullanicibilgi", "serverinfo", "sunucubilgi",
        "8ball", "zar", "yazitura", "yazıtura", "duello", "düello", "sayitahmin", "sayıtahmin",
        "saril", "sarıl", "tokat", "spotify"
    ]
    
    if ctx.command and ctx.command.name in herkese_acik:
        return True
    
    if ctx.author.guild_permissions.administrator:
        return True
    raise commands.CheckFailure("no_admin")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ Bu yönetici komutunu sadece **yöneticiler (Administrator)** kullanabilir!")
        return
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Beklenmeyen hata: {error}")


# ----------------------------------------------------------
# DİNLEYİCİLER (ON_MESSAGE & LÖÖP TASKS)
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

    # 2. SAYI TAHMİN OYUNU
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
# OTOMATİK MESAJ DÖNGÜSÜ (TASK)
# ----------------------------------------------------------
@tasks.loop(minutes=1)
async def auto_message_loop():
    if not auto_message_config["running"] or not auto_message_config["channel_id"]:
        return

    # Dakika sayacını kontrol et
    if not hasattr(auto_message_loop, "counter"):
        auto_message_loop.counter = 0

    auto_message_loop.counter += 1

    if auto_message_loop.counter >= auto_message_config["interval_minutes"]:
        channel = bot.get_channel(auto_message_config["channel_id"])
        if channel and auto_message_config["message"]:
            try:
                await channel.send(auto_message_config["message"])
            except Exception as e:
                print(f"Otomatik mesaj gönderilemedi: {e}")
        auto_message_loop.counter = 0


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
    if not auto_message_loop.is_running():
        auto_message_loop.start()


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
# YARDIM VE BİLGİ KOMUTLARI
# ----------------------------------------------------------

@bot.command(name="yardım", aliases=["yardim", "help"])
async def yardim(ctx):
    mesaj = (
        f"🎮 **Eğlence & Oyun Komutları**\n"
        f"• `{PREFIX}sayitahmin` — Sayı tahmin oyununu başlatır\n"
        f"• `{PREFIX}duello @üye` — Belirtilen üye ile 1v1 kapışır\n"
        f"• `{PREFIX}8ball <soru>` — Mistik küre sorunu yanıtlar\n"
        f"• `{PREFIX}zar` — 1-6 arası zar atar\n"
        f"• `{PREFIX}yazitura` — Yazı mı tura mı atar\n"
        f"• `{PREFIX}saril @üye` / `{PREFIX}tokat @üye` — Etkileşimler\n"
        f"• `{PREFIX}afk [sebep]` — AFK moduna geçer\n\n"
        f"🎵 **Sosyal & Bilgi Komutları**\n"
        f"• `{PREFIX}spotify [@üye]` — Üyenin dinlediği Spotify şarkısını gösterir\n"
        f"• `{PREFIX}avatar [@üye]` — Profil fotoğrafını gösterir\n"
        f"• `{PREFIX}userinfo [@üye]` — Üye detaylı bilgilerini gösterir\n"
        f"• `{PREFIX}serverinfo` — Sunucu istatistiklerini gösterir\n"
        f"• `{PREFIX}ping` — Botun gecikme süresini gösterir\n\n"
        f"📢 **Otomatik Mesaj (Sadece Admin)**\n"
        f"• `{PREFIX}otomesaj-ayarla <kanal_id> <dakika> <mesaj>` — Otomatik duyuru başlatır\n"
        f"• `{PREFIX}otomesaj-kapat` — Otomatik duyuruyu durdurur\n\n"
        f"🛠️ **Moderasyon Komutları (Sadece Admin)**\n"
        f"• `{PREFIX}sil <sayı>` — Belirtilen miktarda mesaj siler\n"
        f"• `{PREFIX}ban @üye [sebep]` | `{PREFIX}unban <ID>` — Ban işlemleri\n"
        f"• `{PREFIX}kick @üye [sebep]` — Üyeyi sunucudan atar\n"
        f"• `{PREFIX}timeout @üye <dk> [sebep]` | `{PREFIX}unmute @üye` — Susturma\n"
        f"• `{PREFIX}warn @üye [sebep]` | `{PREFIX}warnings @üye` — Uyarı sistemi\n"
        f"• `{PREFIX}lock` | `{PREFIX}unlock` — Kanal kilitler/açar\n"
        f"• `{PREFIX}slowmode <saniye>` — Yavaş mod uygular\n"
        f"• `{PREFIX}nick @üye <isim>` | `{PREFIX}rolver` | `{PREFIX}rolal` — Üye yönetimi"
    )
    await ctx.reply(mesaj)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.reply(f"🏓 Pong! Gecikme: **{round(bot.latency * 1000)}ms**")


# --- SPOTIFY KOMUTU ---

@bot.command(name="spotify")
async def spotify_info(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author

    spotify_activity = None
    for act in member.activities:
        if isinstance(act, discord.Spotify):
            spotify_activity = act
            break

    if spotify_activity is None:
        await ctx.reply(f"🎧 **{member.display_name}** şu anda Spotify'da bir şey dinlemiyor (veya Discord etkinlik durumu kapalı).")
        return

    embed = discord.Embed(
        title=f"🎧 {member.display_name} Spotify Dinliyor",
        color=discord.Color.green()
    )
    embed.add_field(name="🎵 Şarkı", value=f"**{spotify_activity.title}**", inline=False)
    embed.add_field(name="👤 Sanatçı", value=", ".join(spotify_activity.artists), inline=True)
    embed.add_field(name="💿 Albüm", value=spotify_activity.album, inline=True)
    embed.set_thumbnail(url=spotify_activity.album_cover_url)
    embed.set_footer(text=f"Şarkı Bağlantısı: {spotify_activity.track_url}")

    await ctx.send(embed=embed)


# --- OTOMATİK MESAJ KOMUTLARI ---

@bot.command(name="otomesaj-ayarla", aliases=["otoduyuru-ayarla"])
async def otomesaj_ayarla(ctx, kanal_id: str = None, dakika: str = None, *, mesaj: str = None):
    if kanal_id is None or dakika is None or mesaj is None or not kanal_id.isdigit() or not dakika.isdigit():
        await ctx.reply(f"⚠️ Kullanım: `{PREFIX}otomesaj-ayarla <kanal_id> <dakika> <mesaj>`\nÖrnek: `{PREFIX}otomesaj-ayarla 123456789 60 Sunucumuza hoş geldiniz!`")
        return

    auto_message_config["channel_id"] = int(kanal_id)
    auto_message_config["interval_minutes"] = int(dakika)
    auto_message_config["message"] = mesaj
    auto_message_config["running"] = True
    auto_message_loop.counter = 0

    await ctx.send(f"📢 **Otomatik Mesaj Ayarlandı!**\n📍 **Kanal:** <#{kanal_id}>\n⏱️ **Süre:** {dakika} dakikada bir\n📝 **Mesaj:** {mesaj}")


@bot.command(name="otomesaj-kapat", aliases=["otoduyuru-kapat"])
async def otomesaj_kapat(ctx):
    auto_message_config["running"] = False
    await ctx.send("🛑 Otomatik mesaj gönderimi durduruldu.")


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

    await ctx.send("🎲 **Sayı Tahmin Oyunu Başladı!**\n1 ile 100 arasında bir sayı tuttum. Tahminlerinizi kanala yazın! (⬆️ Daha büyük / ⬇️ Daha küçük)")


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
        await ctx.reply(f"⚠️ Lütfen bir soru sor! Örnek: `{PREFIX}8ball Bugün şanslı mıyım?`")
        return

    cevaplar = [
        "Kesinlikle evet! ✨", "Şüphesiz öyle. 👍", "Büyük ihtimalle... 🤔",
        "Pek sanmıyorum. 🛑", "İmkansız, unut bunu! ❌", "Zaman gösterir... 🔮",
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
    embed = discord.Embed(description=f"🤗 {ctx.author.mention}, {hedef.mention} kişisine sımsıkı sarıldı!", color=discord.Color.purple())
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
    embed = discord.Embed(description=f"💥 {ctx.author.mention}, {hedef.mention} kişisine osmanlı tokadı yapıştırdı!", color=discord.Color.red())
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


# --- MODERASYON KOMUTLARI ---

@bot.command(name="sil", aliases=["mesajsil", "clear", "purge"])
async def sil(ctx, miktar: str = None):
    if miktar is None or not miktar.isdigit():
        await ctx.reply(f"⚠️ Miktarı belirtin! Örnek: `{PREFIX}sil 50`")
        return

    miktar = int(miktar)
    if miktar < 1 or miktar > 1000:
        await ctx.reply("⚠️ 1 ile 1000 arasında sayı girin!")
        return

    try:
        silinenler = await ctx.channel.purge(limit=miktar + 1)
        toplam_silinen = len(silinenler) - 1
        bilgi = await ctx.send(f"✅ **{max(toplam_silinen, 0)}** mesaj silindi.")
        await asyncio.sleep(5)
        await bilgi.delete()
    except Exception as e:
        print(e)


@bot.command(name="ban")
async def ban(ctx, *, arg: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply("⚠️ Lütfen üyeyi etiketleyin!")
        return

    reason = "Sebep belirtilmedi"
    if arg and len(arg.split(maxsplit=1)) > 1:
        reason = arg.split(maxsplit=1)[1]

    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ **{member}** banlandı.\n📝 Sebep: {reason}")
    except Exception as e:
        print(e)


@bot.command(name="kick")
async def kick(ctx, *, arg: str = None):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply("⚠️ Lütfen üyeyi etiketleyin!")
        return

    reason = "Sebep belirtilmedi"
    if arg and len(arg.split(maxsplit=1)) > 1:
        reason = arg.split(maxsplit=1)[1]

    try:
        await member.kick(reason=reason)
        await ctx.send(f"✅ **{member}** atıldı.\n📝 Sebep: {reason}")
    except Exception as e:
        print(e)


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


@bot.command(name="unmute", aliases=["untimeout"])
async def unmute(ctx, uye: str = None):
    member = await get_mentioned_member(ctx)
    if member:
        await member.timeout(None)
        await ctx.send(f"🔊 **{member}** üzerindeki susturma kaldırıldı.")


@bot.command(name="warn", aliases=["uyar"])
async def warn(ctx, uye: str = None, *, sebep: str = "Sebep belirtilmedi"):
    member = await get_mentioned_member(ctx)
    if member is None:
        await ctx.reply("⚠️ Lütfen üyeyi etiketleyin!")
        return

    guild_id = ctx.guild.id
    user_id = member.id

    if guild_id not in warnings_data:
        warnings_data[guild_id] = {}
    
    warnings_data[guild_id][user_id] = warnings_data[guild_id].get(user_id, 0) + 1
    toplam_uyari = warnings_data[guild_id][user_id]

    await ctx.send(f"⚠️ **{member.mention}** uyarıldı! (Toplam: **{toplam_uyari}**)\n📝 Sebep: {sebep}")

    if toplam_uyari >= 3:
        sure = discord.utils.utcnow() + discord.utils.timedelta(minutes=10)
        try:
            await member.timeout(sure, reason="3 Uyarı sınırına ulaşıldı.")
            await ctx.send(f"🚫 **{member.mention}** 3 uyarı aldığı için **10 dakika** susturuldu!")
            warnings_data[guild_id][user_id] = 0
        except Exception as e:
            print(f"Otomatik mute hatası: {e}")


@bot.command(name="warnings", aliases=["uyarılar", "uyarilar"])
async def warnings(ctx, uye: str = None):
    member = await get_mentioned_member(ctx) or ctx.author
    sayi = warnings_data.get(ctx.guild.id, {}).get(member.id, 0)
    await ctx.reply(f"📊 **{member.display_name}** uyarı sayısı: **{sayi}**")


@bot.command(name="lock", aliases=["kilitle"])
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Kanal kilitlendi.")


@bot.command(name="unlock", aliases=["kilitac"])
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Kanalın kilidi açıldı.")


@bot.command(name="slowmode", aliases=["yavasmod"])
async def slowmode(ctx, saniye: str = None):
    if saniye and saniye.isdigit():
        await ctx.channel.edit(slowmode_delay=int(saniye))
        await ctx.send(f"⏱️ Yavaş mod **{saniye} saniye** olarak ayarlandı.")


@bot.command(name="nick", aliases=["isim"])
async def nick(ctx, uye: str = None, *, yeni_isim: str = None):
    member = await get_mentioned_member(ctx)
    if member and yeni_isim:
        await member.edit(nick=yeni_isim)
        await ctx.send(f"✅ **{member.name}** ismi **{yeni_isim}** yapıldı.")


@bot.command(name="rolver")
async def rolver(ctx, uye: str = None, rol: str = None):
    member = await get_mentioned_member(ctx)
    role = await get_mentioned_role(ctx)
    if member and role:
        await member.add_roles(role)
        await ctx.send(f"✅ **{member.display_name}** kullanıcısına **{role.name}** rolü verildi.")


@bot.command(name="rolal")
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
# 6) RENDER İÇİN KEEP-ALIVE
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
        return
    while True:
        time.sleep(4 * 60)
        try:
            requests.get(url, timeout=10)
        except Exception:
            pass

def keep_alive():
    threading.Thread(target=flask_calistir, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()

# ----------------------------------------------------------
# 7) BOTU BAŞLAT
# ----------------------------------------------------------
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
