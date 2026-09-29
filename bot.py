import os
import sqlite3
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands

# --- 1. CONFIGURAZIONE DATABASE ---
DB_PATH = "bot_data.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS erlc_config (
                guild_id INTEGER PRIMARY KEY,
                api_key TEXT,
                creator_name TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

init_db()

# --- 2. CONFIGURAZIONE BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True  # Necessario per molte funzioni

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'======================================')
    print(f'🤖 BOT ONLINE: {bot.user}')
    print(f'======================================')
    
    activity = discord.Activity(type=discord.ActivityType.listening, name="/stato")
    await bot.change_presence(activity=activity, status=discord.Status.online)
    
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Comandi slash sincronizzati: {len(synced)}")
    except Exception as e:
        print(f"❌ Errore sincronizzazione: {e}")

# --- 3. EVENTO: BENVENUTO ---
@bot.event
async def on_member_join(member):
    with sqlite3.connect(DB_PATH) as db:
        db_cursor = db.cursor()
        db_cursor.execute("SELECT creator_name FROM erlc_config WHERE guild_id = ?", (member.guild.id,))
        row = db_cursor.fetchone()
        nome_creatore = row[0] if row else "il mio sviluppatore"

    canale = discord.utils.get(member.guild.text_channels, name="benvenuto")
    if canale:
        embed = discord.Embed(
            title=f"👋 Benvenuto/a nel server, {member.display_name}!",
            description=f"Ciao! Io sono il bot di gestione ER:LC ufficiale.\n\n"
                        f"🛠️ Realizzato da **{nome_creatore}** per automatizzare RP e sicurezza.\n\n"
                        f"Buon divertimento nella community! 🎉",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"Membro n. {member.guild.member_count}")
        embed.timestamp = discord.utils.utcnow()
        
        await canale.send(content=member.mention, embed=embed)

# --- 4. CHECK CONFIGURAZIONE ---
def check_is_configured():
    async def predicate(interaction: discord.Interaction) -> bool:
        with sqlite3.connect(DB_PATH) as db:
            db_cursor = db.cursor()
            db_cursor.execute("SELECT api_key FROM erlc_config WHERE guild_id = ?", (interaction.guild.id,))
            row = db_cursor.fetchone()
            
        if row is None:
            await interaction.response.send_message(
                "⚠️ **BOT NON CONFIGURATO** ⚠️\n"
                "Un amministratore deve impostare il bot con:\n"
                "`/setup_erlc api_key:LA_TUA_CHIAVE creatore:IL_TUO_NOME`",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

# --- 5. API HELPER ---
async def fetch_erlc_data(endpoint: str = ""):
    headers = {} # Le API verranno passate dai comandi che chiamano questo helper
    # Nota: Questo helper generico non viene usato direttamente, ma lo preparo per future estensioni
    return None

async def get_api_key(guild_id: int) -> str | None:
    with sqlite3.connect(DB_PATH) as db:
        db_cursor = db.cursor()
        db_cursor.execute("SELECT api_key FROM erlc_config WHERE guild_id = ?", (guild_id,))
        row = db_cursor.fetchone()
        return row[0] if row else None

# ==========================================
#          COMANDI
# ==========================================

@bot.tree.command(name="setup_erlc", description="Configurazione iniziale bot (Solo Admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(api_key="Chiave API privata ER:LC", creatore="Nome/Tag del creatore")
async def setup_erlc(interaction: discord.Interaction, api_key: str, creatore: str):
    with sqlite3.connect(DB_PATH) as db:
        db_cursor = db.cursor()
        db_cursor.execute(
            "INSERT INTO erlc_config (guild_id, api_key, creator_name) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET api_key=excluded.api_key, creator_name=excluded.creator_name",
            (interaction.guild.id, api_key, creatore)
        )
        db.commit()
    await interaction.response.send_message(f"✅ Configurazione completata! Creatore: **{creatore}**", ephemeral=True)

@bot.tree.command(name="warn", description="Ammonisce un membro")
@app_commands.checks.has_permissions(moderate_members=True)
@check_is_configured()
@app_commands.describe(membro="Utente da ammonire", motivo="Motivo della sanzione")
async def warn(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    if membro == interaction.user:
        return await interaction.response.send_message("Non puoi ammonire te stesso!", ephemeral=True)
    if membro.top_role >= interaction.user.top_role:
        return await interaction.response.send_message("Non puoi ammonire un utente con un ruolo superiore o uguale!", ephemeral=True)

    with sqlite3.connect(DB_PATH) as db:
        db_cursor = db.cursor()
        db_cursor.execute("INSERT INTO warnings (user_id, guild_id, moderator_id, reason) VALUES (?, ?, ?, ?)", 
                          (membro.id, interaction.guild.id, interaction.user.id, motivo))
        db.commit()
        db_cursor.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?", 
                          (membro.id, interaction.guild.id))
        totale = db_cursor.fetchone()[0]

    await interaction.response.send_message(f"⚠️ **{membro.mention} ammonito!**\n📝 Motivo: `{motivo}`\n🔢 Totale richiami: **{totale}**")
    try: await membro.send(f"Sei stato ammonito in **{interaction.guild.name}**.\n📝 Motivo: `{motivo}`")
    except discord.Forbidden: pass

@bot.tree.command(name="warns", description="Storico ammonizioni di un utente")
@check_is_configured()
@app_commands.describe(membro="Utente da controllare")
async def list_warns(interaction: discord.Interaction, membro: discord.Member):
    with sqlite3.connect(DB_PATH) as db:
        db_cursor = db.cursor()
        db_cursor.execute("SELECT moderator_id, reason, date FROM warnings WHERE user_id = ? AND guild_id = ?", 
                          (membro.id, interaction.guild.id))
        rows = db_cursor.fetchall()

    if not rows:
        return await interaction.response.send_message(f"✅ {membro.mention} non ha richiami.", ephemeral=True)

    msg = f"📋 **Richiami attivi per {membro.display_name}:**\n"
    for i, (mod, motivo, data) in enumerate(rows, 1):
        msg += f"**{i}.** {motivo} | Moderatore: <@{mod}> | {data}\n"
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="ssu", description="Annuncio Server Start Up (Solo Staff/Admin)")
@app_commands.checks.has_permissions(administrator=True)
@check_is_configured()
@app_commands.describe(dettagli="Note aggiuntive per l'apertura")
async def ssu_manuale(interaction: discord.Interaction, dettagli: str = "Il server è ora accessibile. Buon divertimento!"):
    api_key = await get_api_key(interaction.guild.id)
    
    join_code = "N/D"
    if api_key:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://erlc.gg", headers={"Server-Key": api_key}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        join_code = data.get("JoinCode", data.get("join_code", "Non disponibile"))
            except Exception:
                join_code = "Errore nel recupero"

    embed = discord.Embed(
        title="🟢 SERVER START UP (SSU)",
        description="Il server è stato **avviato manualmente** ed è **ONLINE**! 🚀",
        color=discord.Color.green()
    )
    embed.add_field(name="📌 Stato:", value="🔓 Aperto / Online", inline=True)
    embed.add_field(name="🎟️ Join Code:", value=join_code, inline=True)
    embed.add_field(name="📝 Note:", value=dettagli, inline=False)
    embed.set_footer(text=f"Issued by {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stato", description="Mostra lo stato del bot")
@check_is_configured()
async def stato(interaction: discord.Interaction):
    await interaction.response.send_message(f"🟢 Il bot è attivo e funzionante! Latenza: {round(bot.latency * 1000)}ms", ephemeral=True)

# --- AVVIO BOT ---
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("❌ Mancante DISCORD_BOT_TOKEN. Configura il file .env o le variabili d'ambiente.")
    bot.run(TOKEN)
