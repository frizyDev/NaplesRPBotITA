import sqlite3
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands


# --- 1. CONFIGURAZIONE E INIZIALIZZAZIONE DATABASE ---
conn = sqlite3.connect('bot_data.db')
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


cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_patenti (
        user_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        stato_patente TEXT DEFAULT 'Valida'
    )
''')


cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_casellario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        guild_id INTEGER,
        reato TEXT,
        agente_id INTEGER,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')


cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_veicoli (
        targa TEXT PRIMARY KEY,
        user_id INTEGER,
        guild_id INTEGER,
        modello TEXT,
        assicurato TEXT DEFAULT 'Sì'
    )
''')


cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_cittadinanza (
        user_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        nome_cognome TEXT,
        data_nascita TEXT,
        lavoro TEXT,
        storia TEXT,
        stato TEXT DEFAULT 'In Attesa'
    )
''')


cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_arresti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        guild_id INTEGER,
        agente_id INTEGER,
        motivo TEXT,
        tempo_minuti INTEGER,
        cauzione INTEGER,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')


cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_porto_darmi (
        user_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        stato TEXT DEFAULT 'Non Posseduto',
        tipo_licenza TEXT DEFAULT 'Nessuna'
    )
''')


# TABELLA BAN RP/SERVER
cursor.execute('''
    CREATE TABLE IF NOT EXISTS rp_bans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        guild_id INTEGER,
        roblox_username TEXT,
        durata TEXT,
        motivo TEXT,
        staff_id INTEGER,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')


conn.commit()
conn.close()


# --- 2. CONFIGURAZIONE BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


bot = commands.Bot(command_prefix="!", intents=intents)


sondaggi_rp_attivi = {}


@bot.event
async def on_ready():
    print('======================================')
    print(f'🤖 BOT ONLINE: {bot.user}')
    print('======================================')
    
    attivita = discord.Activity(type=discord.ActivityType.listening, name="/stato")
    await bot.change_presence(activity=attivita, status=discord.Status.online)
    
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Sincronizzati con successo {len(synced)} comandi slash!")
    except Exception as e:
        print(f"❌ Errore nella sincronizzazione dei comandi: {e}")


# --- 3. EVENTO BENVENUTO ---
@bot.event
async def on_member_join(member):
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute("SELECT creator_name FROM erlc_config WHERE guild_id = ?", (member.guild.id,))
    row = db_cursor.fetchone()
    db.close()
    
    nome_creatore = row[0] if row else "il mio sviluppatore"
    canale = discord.utils.get(member.guild.text_channels, name="benvenuto")
    
    if canale:
        embed = discord.Embed(
            title=f"👋 Benvenuto/a nel server, {member.display_name}!",
            description=f"Ciao! Io sono il bot di gestione ER:LC ufficiale di questo server.\n\n"
                        f"🛠️ Sono stato interamente programmato da **{nome_creatore}** per automatizzare le sessioni RP e gestire la sicurezza.\n\n"
                        f"Buon divertimento all'interno della community! 🎉",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.defaultavatar.url if hasattr(member, 'defaultavatar') else member.default_avatar.url)
        embed.set_footer(text=f"Membro numero {member.guild.member_count}")
        embed.timestamp = discord.utils.utcnow()
        
        await canale.send(content=member.mention, embed=embed)


# --- 4. CHECK CONFIGURAZIONE ---
def check_is_configured():
    async def predicate(interaction: discord.Interaction) -> bool:
        db = sqlite3.connect('bot_data.db')
        db_cursor = db.cursor()
        db_cursor.execute("SELECT api_key FROM erlc_config WHERE guild_id = ?", (interaction.guild.id,))
        row = db_cursor.fetchone()
        db.close()
        
        if row is None:
            await interaction.response.send_message(
                "⚠️ **SISTEMA COMPROMESSO / NON CONFIGURATO** ⚠️\n"
                "Il bot non può funzionare senza configurazione iniziale.\n"
                "Un **Amministratore** deve prima configurare il bot usando:\n"
                "`/setup_erlc api_key:LA_TUA_CHIAVE creatore:IL_TUO_NOME`", 
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


# --- 5. FUNZIONI API ER:LC ---
async def fetch_erlc_server_info(api_key: str):
    headers = {"Server-Key": api_key}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://api.policeroleplay.community/v1/server", headers=headers) as response:
                if response.status == 200: return await response.json()
                return None
        except Exception: return None


async def fetch_erlc_players(api_key: str):
    headers = {"Server-Key": api_key}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://api.policeroleplay.community/v1/server/players", headers=headers) as response:
                if response.status == 200: return await response.json()
                return None
        except Exception: return None


# --- UI COMPONENTS ---
class SSUView(discord.ui.View):
    def __init__(self, join_code: str):
        super().__init__(timeout=None)
        if join_code and join_code != "N/D":
            url = f"https://www.roblox.com/games/start?placeId=2534724415&launchData={join_code}"
            self.add_item(discord.ui.Button(label="🚀 Entra nel Server", url=url, style=discord.ButtonStyle.link))


class SondaggioRPView(discord.ui.View):
    def __init__(self, orari: list, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id
        for i, orario in enumerate(orari):
            self.add_item(self.CreaPulsanteOrario(label=orario, custom_id=f"voto_{i}"))


    class CreaPulsanteOrario(discord.ui.Button):
        def __init__(self, label: str, custom_id: str):
            super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=custom_id)


        async def callback(self, interaction: discord.Interaction):
            msg_id = self.view.message_id
            if msg_id not in sondaggi_rp_attivi:
                await interaction.response.send_message("❌ Questo sondaggio non è più attivo.", ephemeral=True)
                return


            voti = sondaggi_rp_attivi[msg_id]["voti"]
            voti[interaction.user.id] = self.label
            await interaction.response.send_message(f"✅ Hai votato per l'orario: **{self.label}**!", ephemeral=True)


# --- MODAL & VIEW PER LA CITTADINANZA RP ---
class CittadinanzaStaffView(discord.ui.View):
    def __init__(self, user_id: int, dati_cittadino: dict):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.dati = dati_cittadino


    @discord.ui.button(label="✅ Approva Cittadinanza", style=discord.ButtonStyle.success)
    async def approva(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Solo lo Staff può approvare la cittadinanza!", ephemeral=True)
            return


        db = sqlite3.connect('bot_data.db')
        db_cursor = db.cursor()
        db_cursor.execute("""
            INSERT INTO rp_cittadinanza (user_id, guild_id, nome_cognome, data_nascita, lavoro, storia, stato)
            VALUES (?, ?, ?, ?, ?, ?, 'Approvato')
            ON CONFLICT(user_id) DO UPDATE SET
            nome_cognome=excluded.nome_cognome, data_nascita=excluded.data_nascita,
            lavoro=excluded.lavoro, storia=excluded.storia, stato='Approvato'
        """, (self.user_id, interaction.guild.id, self.dati['nome_cognome'], self.dati['data_nascita'], self.dati['lavoro'], self.dati['storia']))
        db.commit()
        db.close()


        membro = interaction.guild.get_member(self.user_id)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "📜 CITTADINANZA RP - APPROVATA ✅"
        embed.set_footer(text=f"Approvata da {interaction.user.display_name}")


        for item in self.children:
            item.disabled = True


        await interaction.response.edit_message(embed=embed, view=self)


        if membro:
            ruolo_cittadino = discord.utils.get(interaction.guild.roles, name="Cittadino")
            if ruolo_cittadino:
                try: await membro.add_roles(ruolo_cittadino)
                except discord.Forbidden: pass


            try: await membro.send(f"🎉 **Congratulazioni!** La tua richiesta di Cittadinanza RP nel server **{interaction.guild.name}** è stata **APPROVATA** dallo Staff!")
            except discord.Forbidden: pass


    @discord.ui.button(label="❌ Rifiuta", style=discord.ButtonStyle.danger)
    async def rifiuta(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Solo lo Staff può rifiutare la cittadinanza!", ephemeral=True)
            return


        db = sqlite3.connect('bot_data.db')
        db_cursor = db.cursor()
        db_cursor.execute("UPDATE rp_cittadinanza SET stato='Rifiutato' WHERE user_id = ?", (self.user_id,))
        db.commit()
        db.close()


        membro = interaction.guild.get_member(self.user_id)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "📜 CITTADINANZA RP - RIFIUTATA ❌"
        embed.set_footer(text=f"Rifiutata da {interaction.user.display_name}")


        for item in self.children:
            item.disabled = True


        await interaction.response.edit_message(embed=embed, view=self)


        if membro:
            try: await membro.send(f"❌ La tua richiesta di Cittadinanza RP nel server **{interaction.guild.name}** è stata **RIFIUTATA** dallo Staff.")
            except discord.Forbidden: pass


class CittadinanzaModal(discord.ui.Modal, title="Richiesta Cittadinanza RP"):
    nome_cognome = discord.ui.TextInput(
        label="Nome e Cognome RP",
        placeholder="es. Mario Rossi",
        required=True
    )
    data_nascita = discord.ui.TextInput(
        label="Data di Nascita RP",
        placeholder="es. 15/04/1995",
        required=True
    )
    lavoro = discord.ui.TextInput(
        label="Lavoro / Professione desiderata",
        placeholder="es. Meccanico, Civile, Disoccupato...",
        required=True
    )
    storia = discord.ui.TextInput(
        label="Breve storia/background del personaggio",
        style=discord.TextStyle.paragraph,
        placeholder="Racconta brevemente chi è il tuo personaggio e i suoi obiettivi...",
        required=True,
        max_length=500
    )


    async def on_submit(self, interaction: discord.Interaction):
        canale_staff = discord.utils.get(interaction.guild.text_channels, name="richieste-cittadinanza") or interaction.channel


        dati_cittadino = {
            "nome_cognome": self.nome_cognome.value,
            "data_nascita": self.data_nascita.value,
            "lavoro": self.lavoro.value,
            "storia": self.storia.value
        }


        embed = discord.Embed(
            title="📜 NUOVA RICHIESTA CITTADINANZA RP",
            color=discord.Color.gold()
        )
        embed.add_field(name="👤 Utente Discord:", value=interaction.user.mention, inline=True)
        embed.add_field(name="📛 Nome e Cognome RP:", value=self.nome_cognome.value, inline=True)
        embed.add_field(name="📅 Data di Nascita:", value=self.data_nascita.value, inline=True)
        embed.add_field(name="💼 Professione:", value=self.lavoro.value, inline=False)
        embed.add_field(name="📖 Background Personaggio:", value=self.storia.value, inline=False)
        embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.default_avatar.url)
        embed.timestamp = discord.utils.utcnow()


        view = CittadinanzaStaffView(user_id=interaction.user.id, dati_cittadino=dati_cittadino)
        await canale_staff.send(embed=embed, view=view)


        await interaction.response.send_message(
            "✅ **Modulo inviato con successo!** La tua richiesta di cittadinanza è stata inoltrata allo Staff per l'approvazione.",
            ephemeral=True
        )




# ==========================================
#          COMANDI DI CONFIGURAZIONE
# ==========================================


@bot.tree.command(name="setup_erlc", description="Configura il bot inserendo la chiave API ER:LC e il creatore (Solo Admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(api_key="La chiave segreta API generata nel tuo server ER:LC", creatore="Il tuo nome o tag")
async def setup_erlc(interaction: discord.Interaction, api_key: str, creatore: str):
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute(
        "INSERT INTO erlc_config (guild_id, api_key, creator_name) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET api_key=excluded.api_key, creator_name=excluded.creator_name",
        (interaction.guild.id, api_key, creatore)
    )
    db.commit()
    db.close()
    await interaction.response.send_message(f"✅ **Configurazione completata!** Creatore impostato su: **{creatore}**.", ephemeral=True)




# ==========================================
#          COMANDI DI SICUREZZA / MOD
# ==========================================


# --- COMANDO BAN ESCLUSIVO PER LO STAFF ---
@bot.tree.command(name="ban_rp", description="Banna un utente dal Server e registra la sanzione (Solo Staff)")
@app_commands.checks.has_permissions(moderate_members=True)
@check_is_configured()
@app_commands.describe(
    membro="L'utente Discord da bannare",
    roblox_username="Username Roblox dell'utente",
    durata="Durata del ban (es. 24 Ore, 3 Giorni, Permanente)",
    motivo="Motivo dettagliato del ban"
)
async def ban_rp(
    interaction: discord.Interaction, 
    membro: discord.Member, 
    roblox_username: str, 
    durata: str, 
    motivo: str
):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Non puoi bannare te stesso!", ephemeral=True)
        return
    if membro.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Non puoi bannare un membro dello staff con un ruolo pari o superiore al tuo!", ephemeral=True)
        return


    # Registrazione nel database
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute(
        "INSERT INTO rp_bans (user_id, guild_id, roblox_username, durata, motivo, staff_id) VALUES (?, ?, ?, ?, ?, ?)",
        (membro.id, interaction.guild.id, roblox_username, durata, motivo, interaction.user.id)
    )
    db.commit()
    db.close()


    # Tentativo di avviso in privato all'utente
    try:
        await membro.send(
            f"⛔ **SEI STATO BANNATO DAL SERVER {interaction.guild.name}** ⛔\n\n"
            f"👤 **Account Roblox:** `{roblox_username}`\n"
            f"⏱️ **Durata:** {durata}\n"
            f"📝 **Motivo:** {motivo}\n"
            f"👮 **Membro Staff:** {interaction.user.display_name}"
        )
    except discord.Forbidden:
        pass


    # Esecuzione del Ban Discord se la durata è Permanente o a discrezione
    try:
        await membro.ban(reason=f"Ban RP da {interaction.user.display_name}: {motivo} | Roblox: {roblox_username}")
    except discord.Forbidden:
        await interaction.response.send_message("⚠️ Ho registrato il ban nel database ma non ho i permessi Discord per espellere l'utente dal server!", ephemeral=True)
        return


    # Generazione Embed del Ban
    embed = discord.Embed(
        title="⛔ BAN RP & SANZIONE APPLICATA",
        description="Un nuovo provvedimento disciplinare è stato registrato ed eseguito dallo Staff.",
        color=discord.Color.dark_red()
    )
    embed.add_field(name="👤 Utente Discord:", value=f"{membro.mention} (`{membro.id}`)", inline=True)
    embed.add_field(name="🎮 Account Roblox:", value=f"`{roblox_username}`", inline=True)
    embed.add_field(name="⏱️ Durata Ban:", value=f"**{durata}**", inline=True)
    embed.add_field(name="📝 Motivo Sanzione:", value=motivo, inline=False)
    embed.add_field(name="👮 Moderatore Staff:", value=interaction.user.mention, inline=True)
    embed.set_thumbnail(url=membro.avatar.url if membro.avatar else membro.default_avatar.url)
    embed.set_footer(text=f"Server: {interaction.guild.name}")
    embed.timestamp = discord.utils.utcnow()


    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="warn", description="Ammonisce un membro del server")
@app_commands.checks.has_permissions(moderate_members=True)
@check_is_configured()
@app_commands.describe(membro="L'utente da ammonire", motivo="Il motivo della sanzione")
async def warn(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    if membro == interaction.user:
        await interaction.response.send_message("Non puoi ammonire te stesso!", ephemeral=True)
        return
    if membro.top_role >= interaction.user.top_role:
        await interaction.response.send_message("Non puoi ammonire un utente con un ruolo superiore o uguale al tuo!", ephemeral=True)
        return


    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute("INSERT INTO warnings (user_id, guild_id, moderator_id, reason) VALUES (?, ?, ?, ?)", 
                      (membro.id, interaction.guild.id, interaction.user.id, motivo))
    db.commit()
    db_cursor.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?", (membro.id, interaction.guild.id))
    totale_warns = db_cursor.fetchone()[0]
    db.close()


    await interaction.response.send_message(f"⚠️ **{membro.mention} è stato ammonito!**\n**Motivo:** {motivo}\n**Conteggio totale:** {totale_warns} richiamo/i.")
    try: await membro.send(f"Sei stato ammonito nel server **{interaction.guild.name}**.\n**Motivo:** {motivo}")
    except discord.Forbidden: pass


@bot.tree.command(name="warns", description="Visualizza lo storico dei richiami di un utente")
@check_is_configured()
@app_commands.describe(membro="L'utente da controllare")
async def list_warns(interaction: discord.Interaction, membro: discord.Member):
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute("SELECT moderator_id, reason, date FROM warnings WHERE user_id = ? AND guild_id = ?", (membro.id, interaction.guild.id))
    rows = db_cursor.fetchall()
    db.close()


    if not rows:
        await interaction.response.send_message(f"✅ {membro.mention} non ha alcuna ammonizione a carico.", ephemeral=True)
        return


    messaggio = f"📋 **Richiami attivi per {membro.display_name}:**\n"
    for i, row in enumerate(rows, 1):
        messaggio += f"**{i}.** Motivo: *{row[1]}* | Moderatore: <@{row[0]}>\n"
    await interaction.response.send_message(messaggio, ephemeral=True)




# ==========================================
#      COMANDI GESTIONE / ANNUNCI SERVER
# ==========================================


@bot.tree.command(name="ssu", description="Invia l'annuncio di Server Start Up (Solo Staff)")
@app_commands.checks.has_permissions(administrator=True)
@check_is_configured()
@app_commands.describe(dettagli="Informazioni aggiuntive per l'apertura")
async def ssu_manuale(interaction: discord.Interaction, dettagli: str = "Il server è ora accessibile a tutti i giocatori. Buon divertimento!"):
    await interaction.response.defer()


    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute("SELECT api_key FROM erlc_config WHERE guild_id = ?", (interaction.guild.id,))
    api_key = db_cursor.fetchone()[0]
    db.close()


    join_code = "N/D"
    erlc_data = await fetch_erlc_server_info(api_key)
    if erlc_data: join_code = erlc_data.get("JoinCode", "Non disponibile")


    embed = discord.Embed(
        title="🟢 SERVER START UP (SSU)", 
        description="Il server è stato **avviato** ed è ora **ONLINE**! 🚀", 
        color=discord.Color.green()
    )
    embed.add_field(name="📌 Stato:", value="🔓 Aperto / Online", inline=True)
    embed.add_field(name="🔑 Codice d'accesso:", value=f"`{join_code}`", inline=True)
    embed.add_field(name="📝 Note dallo Staff:", value=dettagli, inline=False)
    embed.set_footer(text=f"Avviato da {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()


    view = SSUView(join_code)
    await interaction.followup.send(content="@everyone", embed=embed, view=view)


@bot.tree.command(name="ssd", description="Invia l'annuncio di Server Shut Down (Solo Staff)")
@app_commands.checks.has_permissions(administrator=True)
@check_is_configured()
@app_commands.describe(motivo="Motivo della chiusura del server")
async def ssd_manuale(interaction: discord.Interaction, motivo: str = "La sessione RP è terminata. Grazie a tutti per aver partecipato!"):
    embed = discord.Embed(
        title="🔴 SERVER SHUT DOWN (SSD)", 
        description="Il server è stato **chiuso**. La sessione RP è terminata.", 
        color=discord.Color.red()
    )
    embed.add_field(name="📌 Stato:", value="🔒 Chiuso / Offline", inline=True)
    embed.add_field(name="📝 Motivo:", value=motivo, inline=False)
    embed.set_footer(text=f"Chiuso da {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()


    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stato", description="Mostra lo stato in tempo reale e i giocatori connessi su ER:LC")
@check_is_configured()
async def stato_server(interaction: discord.Interaction):
    await interaction.response.defer()


    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute("SELECT api_key FROM erlc_config WHERE guild_id = ?", (interaction.guild.id,))
    api_key = db_cursor.fetchone()[0]
    db.close()


    erlc_data = await fetch_erlc_server_info(api_key)
    players_data = await fetch_erlc_players(api_key)


    if not erlc_data:
        await interaction.followup.send("❌ Impossibile recuperare i dati da ER:LC. Verifica la chiave API.", ephemeral=True)
        return


    nome_server = erlc_data.get("Name", "Server ER:LC")
    giocatori_online = erlc_data.get("Players", 0)
    max_giocatori = erlc_data.get("MaxPlayers", 0)
    join_code = erlc_data.get("JoinCode", "N/D")


    embed = discord.Embed(title=f"📊 Stato Server: {nome_server}", color=discord.Color.blue())
    embed.add_field(name="👥 Giocatori Online:", value=f"**{giocatori_online} / {max_giocatori}**", inline=True)
    embed.add_field(name="🔑 Codice d'accesso:", value=f"`{join_code}`", inline=True)


    if players_data and isinstance(players_data, list) and len(players_data) > 0:
        lista_nomi = [p.get("Player", "Sconosciuto") for p in players_data[:15]]
        testo_giocatori = "\n".join([f"• {nome}" for nome in lista_nomi])
        if len(players_data) > 15:
            testo_giocatori += f"\n*...e altri {len(players_data) - 15} giocatori.*"
        embed.add_field(name="📜 Giocatori in gioco:", value=testo_giocatori, inline=False)


    await interaction.followup.send(embed=embed)




# ==========================================
#          COMANDI SONDAGGI RP
# ==========================================


@bot.tree.command(name="sondaggio_rp", description="Crea un sondaggio per votare l'orario della sessione RP")
@app_commands.checks.has_permissions(administrator=True)
@check_is_configured()
@app_commands.describe(orario1="Primo orario", orario2="Secondo orario", orario3="Terzo orario opzionale", orario4="Quarto orario opzionale")
async def sondaggio_rp(interaction: discord.Interaction, orario1: str, orario2: str, orario3: str = None, orario4: str = None):
    orari = [o for o in [orario1, orario2, orario3, orario4] if o is not None]


    embed = discord.Embed(
        title="🗓️ SONDAGGIO PROSSIMA SESSIONE RP",
        description="Seleziona l'orario in cui sei disponibile a partecipare cliccando sui pulsanti!",
        color=discord.Color.purple()
    )
    lista_testo = "\n".join([f"🔹 **{o}**" for o in orari])
    embed.add_field(name="Opzioni orario:", value=lista_testo, inline=False)


    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()


    view = SondaggioRPView(orari, msg.id)
    await interaction.edit_original_response(view=view)
    sondaggi_rp_attivi[msg.id] = {"orari": orari, "voti": {}}


@bot.tree.command(name="chiudi_sondaggio", description="Chiude un sondaggio RP e proclama l'orario vincitore")
@app_commands.checks.has_permissions(administrator=True)
@check_is_configured()
@app_commands.describe(id_messaggio="L'ID del messaggio del sondaggio")
async def chiudi_sondaggio(interaction: discord.Interaction, id_messaggio: str):
    try: msg_id = int(id_messaggio)
    except ValueError:
        await interaction.response.send_message("❌ ID non valido.", ephemeral=True)
        return


    if msg_id not in sondaggi_rp_attivi:
        await interaction.response.send_message("❌ Nessun sondaggio attivo con questo ID.", ephemeral=True)
        return


    dati = sondaggi_rp_attivi[msg_id]
    voti = dati["voti"]
    conteggi = {orario: 0 for orario in dati["orari"]}
    for voto in voti.values():
        if voto in conteggi: conteggi[voto] += 1


    orario_vincente = max(conteggi, key=conteggi.get) if conteggi else "Nessun voto"


    embed = discord.Embed(title="📊 SONDAGGIO CONCLUSO", color=discord.Color.gold())
    risultati_testo = "\n".join([f"• **{o}**: {conteggi[o]} voti" for o in dati["orari"]])
    embed.add_field(name="Risultati finali:", value=risultati_testo, inline=False)
    embed.add_field(name="🏆 Orario Vincitore:", value=f"👉 **{orario_vincente}**", inline=False)


    del sondaggi_rp_attivi[msg_id]
    await interaction.response.send_message(embed=embed)




# ==========================================
#       SISTEMA CAD / MDT & COMANDI RP
# ==========================================


@bot.tree.command(name="cittadinanza", description="Richiedi la cittadinanza RP del server tramite modulo")
@check_is_configured()
async def cittadinanza(interaction: discord.Interaction):
    await interaction.response.send_modal(CittadinanzaModal())


@bot.tree.command(name="carta_identita", description="Mostra la Carta d'Identità RP ufficiale dell'utente")
@check_is_configured()
@app_commands.describe(membro="Seleziona l'utente di cui visualizzare il documento")
async def carta_identita(interaction: discord.Interaction, membro: discord.Member = None):
    target = membro or interaction.user
    
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    
    db_cursor.execute("SELECT nome_cognome, data_nascita, lavoro, storia, stato FROM rp_cittadinanza WHERE user_id = ?", (target.id,))
    row_citt = db_cursor.fetchone()
    
    db_cursor.execute("SELECT stato_patente FROM rp_patenti WHERE user_id = ?", (target.id,))
    row_pat = db_cursor.fetchone()
    
    db_cursor.execute("SELECT stato, tipo_licenza FROM rp_porto_darmi WHERE user_id = ?", (target.id,))
    row_armi = db_cursor.fetchone()
    
    db.close()


    stato_citt = row_citt[4] if row_citt else "Non Richiesta"
    if stato_citt != "Approvato":
        await interaction.response.send_message(f"⚠️ **{target.display_name}** non possiede ancora una cittadinanza approvata nel server!", ephemeral=True)
        return


    nome_cognome = row_citt[0]
    data_nascita = row_citt[1]
    lavoro = row_citt[2]
    stato_patente = row_pat[0] if row_pat else "Valida"
    porto_darmi = f"{row_armi[0]} ({row_armi[1]})" if row_armi else "Non Posseduto"


    embed = discord.Embed(title=f"🪪 CARTA D'IDENTITÀ RP", color=discord.Color.dark_gold())
    embed.set_thumbnail(url=target.avatar.url if target.avatar else target.default_avatar.url)
    embed.add_field(name="📛 Nome e Cognome:", value=nome_cognome, inline=True)
    embed.add_field(name="📅 Data di Nascita:", value=data_nascita, inline=True)
    embed.add_field(name="💼 Professione:", value=lavoro, inline=True)
    embed.add_field(name="🪪 Patente di Guida:", value=stato_patente, inline=True)
    embed.add_field(name="🔫 Porto d'Armi:", value=porto_darmi, inline=True)
    embed.add_field(name="👤 Utente Discord:", value=target.mention, inline=True)
    embed.set_footer(text=f"Stato Cittadinanza: {stato_citt} ✅")
    embed.timestamp = discord.utils.utcnow()


    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="arresto", description="Esegue e registra l'arresto di un cittadino (Solo Forze dell'Ordine)")
@check_is_configured()
@app_commands.describe(membro="Il cittadino da arrestare", minuti="Tempo di detenzione in minuti", cauzione="Importo cauzione (€/$)", motivo="Motivo o reati commessi")
async def arresto(interaction: discord.Interaction, membro: discord.Member, minuti: int, cauzione: int, motivo: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Solo gli agenti/staff autorizzati possono effettuare arresti!", ephemeral=True)
        return


    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()
    db_cursor.execute(
        "INSERT INTO rp_arresti (user_id, guild_id, agente_id, motivo, tempo_minuti, cauzione) VALUES (?, ?, ?, ?, ?, ?)",
        (membro.id, interaction.guild.id, interaction.user.id, motivo, minuti, cauzione)
    )
    db_cursor.execute("INSERT INTO rp_casellario (user_id, guild_id, reato, agente_id) VALUES (?, ?, ?, ?)",
                      (membro.id, interaction.guild.id, f"Arresto: {motivo}", interaction.user.id))
    db.commit()
    db.close()


    embed = discord.Embed(title="🚨 VERBALE DI ARRESTO E DETENZIONE", color=discord.Color.dark_red())
    embed.add_field(name="🔒 Detenuto:", value=membro.mention, inline=True)
    embed.add_field(name="👮 Agente Operante:", value=interaction.user.mention, inline=True)
    embed.add_field(name="⏱️ Tempo di Detenzione:", value=f"**{minuti} minuti**", inline=False)
    embed.add_field(name="💵 Cauzione:", value=f"**{cauzione} €/$**", inline=True)
    embed.add_field(name="📝 Capi d'Accusa / Motivo:", value=motivo, inline=False)
    embed.timestamp = discord.utils.utcnow()


    await interaction.response.send_message(embed=embed)


    try:
        await membro.send(
            f"🚨 **SEI STATO ARRESTATO!**\n"
            f"Server: **{interaction.guild.name}**\n"
            f"⏱️ **Tempo:** {minuti} minuti | 💵 **Cauzione:** {cauzione} €/$\n"
            f"📝 **Motivo:** {motivo}"
        )
    except discord.Forbidden: pass


@bot.tree.command(name="licenza_armi", description="Gestisci o verifica il Porto d'Armi di un utente")
@check_is_configured()
@app_commands.describe(membro="L'utente da verificare o modificare", azione="Azione da svolgere", tipo="Tipo di arma (Solo per rilascio)")
@app_commands.choices(azione=[
    app_commands.Choice(name="🔍 Verifica Stato", value="CONTROLLA"),
    app_commands.Choice(name="✅ Rilascia Licenza", value="RILASCIA"),
    app_commands.Choice(name="❌ Revoca Licenza", value="REVOCA")
])
@app_commands.choices(tipo=[
    app_commands.Choice(name="🔫 Difesa Personale (Leggera)", value="Leggera"),
    app_commands.Choice(name="💥 Armi da Caccia/Tiro", value="Sportivo"),
    app_commands.Choice(name="🛡️ Licenza Tattica / Speciale", value="Speciale")
])
async def licenza_armi(interaction: discord.Interaction, membro: discord.Member, azione: app_commands.Choice[str], tipo: app_commands.Choice[str] = None):
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()


    if azione.value == "CONTROLLA":
        db_cursor.execute("SELECT stato, tipo_licenza FROM rp_porto_darmi WHERE user_id = ?", (membro.id,))
        row = db_cursor.fetchone()
        db.close()


        stato = row[0] if row else "Non Posseduto"
        tipo_l = row[1] if row else "Nessuna"
        
        embed = discord.Embed(title=f"🔫 Porto d'Armi RP: {membro.display_name}", color=discord.Color.blue())
        embed.add_field(name="Stato Licenza:", value=f"**{stato}**", inline=True)
        embed.add_field(name="Tipologia:", value=f"**{tipo_l}**", inline=True)
        await interaction.response.send_message(embed=embed)


    elif azione.value == "RILASCIA":
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Solo lo Staff o le Autorità possono rilasciare licenze!", ephemeral=True)
            db.close()
            return


        tipo_selezionato = tipo.value if tipo else "Leggera"
        db_cursor.execute(
            "INSERT INTO rp_porto_darmi (user_id, guild_id, stato, tipo_licenza) VALUES (?, ?, 'Valido', ?) "
            "ON CONFLICT(user_id) DO UPDATE SET stato='Valido', tipo_licenza=excluded.tipo_licenza",
            (membro.id, interaction.guild.id, tipo_selezionato)
        )
        db.commit()
        db.close()


        await interaction.response.send_message(f"✅ Rilasciato **Porto d'Armi ({tipo_selezionato})** a {membro.mention}!")


    elif azione.value == "REVOCA":
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Solo lo Staff o le Autorità possono revocare licenze!", ephemeral=True)
            db.close()
            return


        db_cursor.execute(
            "INSERT INTO rp_porto_darmi (user_id, guild_id, stato, tipo_licenza) VALUES (?, ?, 'Revocato', 'Nessuna') "
            "ON CONFLICT(user_id) DO UPDATE SET stato='Revocato', tipo_licenza='Nessuna'",
            (membro.id, interaction.guild.id)
        )
        db.commit()
        db.close()


        await interaction.response.send_message(f"❌ Il Porto d'Armi di {membro.mention} è stato **REVOCATO**!")


@bot.tree.command(name="patente", description="Mostra o aggiorna lo stato della patente di guida RP")
@check_is_configured()
@app_commands.describe(membro="L'utente di cui controllare o modificare la patente", nuovo_stato="Modifica stato (Solo Staff/Fazioni)")
@app_commands.choices(nuovo_stato=[
    app_commands.Choice(name="Valida", value="Valida"),
    app_commands.Choice(name="Sospesa", value="Sospesa"),
    app_commands.Choice(name="Revocata", value="Revocata")
])
async def patente(interaction: discord.Interaction, membro: discord.Member, nuovo_stato: app_commands.Choice[str] = None):
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()


    if nuovo_stato:
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Non hai i permessi per modificare la patente!", ephemeral=True)
            db.close()
            return
        
        db_cursor.execute("INSERT INTO rp_patenti (user_id, guild_id, stato_patente) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET stato_patente=excluded.stato_patente", (membro.id, interaction.guild.id, nuovo_stato.value))
        db.commit()
        db.close()
        await interaction.response.send_message(f"🪪 Patente di {membro.mention} aggiornata a: **{nuovo_stato.value}**.")
    else:
        db_cursor.execute("SELECT stato_patente FROM rp_patenti WHERE user_id = ?", (membro.id,))
        row = db_cursor.fetchone()
        db.close()


        stato = row[0] if row else "Valida"
        emoji = "🟢" if stato == "Valida" else ("🟡" if stato == "Sospesa" else "🔴")


        embed = discord.Embed(title=f"🪪 Patente di Guida RP: {membro.display_name}", color=discord.Color.blue())
        embed.add_field(name="Stato Attuale:", value=f"{emoji} **{stato}**", inline=True)
        embed.set_thumbnail(url=membro.avatar.url if membro.avatar else membro.defaultavatar.url)
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="casellario", description="Mostra o aggiunge un reato al casellario giudiziario di un utente")
@check_is_configured()
@app_commands.describe(membro="L'utente da controllare", aggiungi_reato="Aggiungi una condotta illecita (Solo Forze dell'Ordine)")
async def casellario(interaction: discord.Interaction, membro: discord.Member, aggiungi_reato: str = None):
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()


    if aggiungi_reato:
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Non sei autorizzato ad aggiungere precedenti penali!", ephemeral=True)
            db.close()
            return


        db_cursor.execute("INSERT INTO rp_casellario (user_id, guild_id, reato, agente_id) VALUES (?, ?, ?, ?)", (membro.id, interaction.guild.id, aggiungi_reato, interaction.user.id))
        db.commit()
        db.close()
        await interaction.response.send_message(f"🚨 Aggiunto al casellario di {membro.mention}: *{aggiungi_reato}*.")
    else:
        db_cursor.execute("SELECT reato, agente_id, date FROM rp_casellario WHERE user_id = ? AND guild_id = ?", (membro.id, interaction.guild.id))
        rows = db_cursor.fetchall()
        db.close()


        if not rows:
            await interaction.response.send_message(f"✅ **{membro.display_name}** ha un casellario giudiziario pulito.", ephemeral=True)
            return


        embed = discord.Embed(title=f"🏛️ Casellario Giudiziario RP: {membro.display_name}", color=discord.Color.dark_red())
        for i, row in enumerate(rows, 1):
            embed.add_field(name=f"Reato #{i}", value=f"• **Descrizione:** {row[0]}\n• **Agente:** <@{row[1]}>\n• **Data:** {row[2][:10]}", inline=False)
        
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="chiamata_emergenza", description="Invia una chiamata di emergenza (911 / 112) ai soccorsi")
@check_is_configured()
@app_commands.describe(tipo="Tipo di intervento richiesto", posizione="La tua posizione in mappa", dettagli="Dettagli situazione")
@app_commands.choices(tipo=[
    app_commands.Choice(name="🚨 Polizia / Forze dell'Ordine", value="POLIZIA"),
    app_commands.Choice(name="🚑 Ambulanza / Medici", value="MEDICI"),
    app_commands.Choice(name="🚒 Vigili del Fuoco", value="VIGILI DEL FUOCO")
])
async def chiamata_emergenza(interaction: discord.Interaction, tipo: app_commands.Choice[str], posizione: str, dettagli: str):
    embed = discord.Embed(
        title=f"📞 CHIAMATA DI EMERGENZA (911/112) - {tipo.value}",
        description=f"**Chiamante:** {interaction.user.mention}\n**Posizione:** 📍 `{posizione}`\n\n**Dettagli Chiamata:**\n{dettagli}",
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else interaction.user.defaultavatar.url)
    embed.timestamp = discord.utils.utcnow()
    
    await interaction.response.send_message(content="🚨 **CHIAMATA DI EMERGENZA INVIATA AI SOCCORSI!**", embed=embed)


@bot.tree.command(name="multa", description="Notifica ed emette un verbale/multa RP verso un cittadino")
@check_is_configured()
@app_commands.describe(membro="Il cittadino da sanzionare", importo="Importo della sanzione (€/$)", motivo="Violazione commessa")
async def multa(interaction: discord.Interaction, membro: discord.Member, importo: int, motivo: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Solo gli agenti/staff autorizzati possono emettere sanzioni!", ephemeral=True)
        return


    embed = discord.Embed(title="🧾 VERBALE DI CONTESTAZIONE SANZIONE RP", color=discord.Color.gold())
    embed.add_field(name="👤 Destinatario:", value=membro.mention, inline=True)
    embed.add_field(name="👮 Agente Accertatore:", value=interaction.user.mention, inline=True)
    embed.add_field(name="💰 Importo da pagare:", value=f"**{importo} €/$**", inline=False)
    embed.add_field(name="📝 Motivazione / Violazione:", value=motivo, inline=False)
    embed.timestamp = discord.utils.utcnow()


    await interaction.response.send_message(embed=embed)
    try: await membro.send(f"⚠️ Ti è stata emessa una multa di **{importo} €/$** nel server **{interaction.guild.name}**.\n**Motivo:** {motivo}")
    except discord.Forbidden: pass


@bot.tree.command(name="scheda_veicolo", description="Registra o cerca informazioni su un veicolo RP tramite la targa")
@check_is_configured()
@app_commands.describe(targa="La targa del veicolo", modello="Modello/Colore dell'auto", proprietario="Proprietario")
async def scheda_veicolo(interaction: discord.Interaction, targa: str, modello: str = None, proprietario: discord.Member = None):
    targa_pulita = targa.upper().strip()
    db = sqlite3.connect('bot_data.db')
    db_cursor = db.cursor()


    if modello and proprietario:
        db_cursor.execute("INSERT INTO rp_veicoli (targa, user_id, guild_id, modello) VALUES (?, ?, ?, ?) ON CONFLICT(targa) DO UPDATE SET modello=excluded.modello, user_id=excluded.user_id", (targa_pulita, proprietario.id, interaction.guild.id, modello))
        db.commit()
        db.close()
        await interaction.response.send_message(f"🚘 Veicolo con targa **[{targa_pulita}]** inserito nel registro Motorizzazione!")
    else:
        db_cursor.execute("SELECT user_id, modello, assicurato FROM rp_veicoli WHERE targa = ? AND guild_id = ?", (targa_pulita, interaction.guild.id))
        row = db_cursor.fetchone()
        db.close()


        if not row:
            await interaction.response.send_message(f"❌ Nessun veicolo trovato con targa **[{targa_pulita}]**.", ephemeral=True)
            return


        embed = discord.Embed(title=f"🚘 Scheda Veicolo Targa: [{targa_pulita}]", color=discord.Color.dark_gray())
        embed.add_field(name="Modello/Colore:", value=row[1], inline=True)
        embed.add_field(name="Proprietario:", value=f"<@{row[0]}>", inline=True)
        embed.add_field(name="Assicurazione:", value=f"✅ {row[2]}", inline=True)
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="annuncio_fazione", description="Pubblica un comunicato ufficiale da parte di una Fazione")
@check_is_configured()
@app_commands.describe(fazione="Fazione mittente", titolo="Titolo comunicato", messaggio="Contenuto annuncio")
@app_commands.choices(fazione=[
    app_commands.Choice(name="🚔 Dipartimento di Polizia / LSPD", value="POLIZIA"),
    app_commands.Choice(name="🚑 Sanità & Soccorso / EMS", value="EMS"),
    app_commands.Choice(name="🚒 Vigili del Fuoco / Fire Dept", value="VIGILI DEL FUOCO"),
    app_commands.Choice(name="🏛 Governo / Municipio", value="GOVERNO")
])
async def annuncio_fazione(interaction: discord.Interaction, fazione: app_commands.Choice[str], titolo: str, messaggio: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Non sei autorizzato ad inviare comunicati!", ephemeral=True)
        return


    colori = {
        "POLIZIA": discord.Color.blue(),
        "EMS": discord.Color.red(),
        "VIGILI DEL FUOCO": discord.Color.orange(),
        "GOVERNO": discord.Color.dark_teal()
    }


    embed = discord.Embed(
        title=f"📢 COMUNICATO UFFICIALE - {fazione.name.upper()}",
        description=f"### {titolo}\n\n{messaggio}",
        color=colori.get(fazione.value, discord.Color.default())
    )
    embed.set_footer(text=f"Rilasciato da: {interaction.user.display_name}")
    embed.timestamp = discord.utils.utcnow()


    await interaction.response.send_message(embed=embed)


# --- AVVIO BOT ---
bot.run("IL_TUO_TOKEN_QUI")
