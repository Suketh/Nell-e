# Nellie Server Handoff

Det här dokumentet är tänkt som ett snabbt handoff till Codex eller en människa på serverdatorn.

## Mål

Nellie kör som desktop-app på klientdatorn och ska använda:

- `XTTS v2` lokalt för TTS
- `Voxtral` på separat serverdator för STT

Klienten ska kunna skicka mikrofonljud till en OpenAI-kompatibel transkriptionsendpoint.

## Klientdator

Det här är Nellie-klienten.

- Klient-IP: `10.146.64.49`
- Projektrot:
  - `c:\Users\suket\Desktop\Pythonprojekt\stor\nellie_fresh`
- Python-miljö:
  - lokal `.venv`
- Appstart:
  - `.\run_local.bat`

## Hur Nellie är konfigurerad

Aktiv riktning i projektet:

- TTS:
  - `XTTS v2`
- STT:
  - `Voxtral self-hosted` som föredragen väg
  - `Local Whisper` som fallback

Relevant klientkonfig i `config.yaml`:

```yaml
stt:
  engine: faster_whisper
  prefer_voxtral_when_configured: true
  voxtral_mode: self_hosted
  voxtral_self_hosted_url: http://10.156.64.136:8080
  voxtral_self_hosted_enabled: true
  voxtral_self_hosted_autostart: false
  voxtral_model: voxtral-mini-latest
```

## Vad servern måste exponera

Nellie förväntar sig följande:

1. Health-check:

```text
GET /health
```

Det bör returnera `200 OK`.

2. OpenAI-kompatibel transkribering:

```text
POST /v1/audio/transcriptions
```

Request-format:

- `multipart/form-data`
- fält:
  - `file`
  - `model`
  - `language`

Svar:

```json
{
  "text": "transcribed text here"
}
```

Detta matchar hur Nellie skickar data i:

- `services/audio/stt_voxtral.py`

## Serverkrav

Servern måste:

- lyssna på LAN, inte bara `127.0.0.1`
- helst binda till:
  - `0.0.0.0:8080`
  - eller specifikt `10.156.64.136:8080`
- tillåta inkommande TCP på port `8080`

## Nätverksbild

Klient:

- `10.146.64.49`

Server:

- `10.156.64.136`

Det betyder att klient och server ligger i olika `10.x`-subnät. Ping har fungerat mellan dem, så viss routing finns, men TCP `8080` har varit instabil eller blockerad i perioder.

## Test från klientdatorn

När servern är rätt exponerad ska detta fungera från Nellie-klienten:

```powershell
curl.exe -i http://10.156.64.136:8080/health
curl.exe -i -X POST http://10.156.64.136:8080/v1/audio/transcriptions
Test-NetConnection 10.156.64.136 -Port 8080
```

Förväntat:

- `health` ska ge `HTTP 200`
- `POST /v1/audio/transcriptions` ska åtminstone svara, även om tom request ger `400`
- `TcpTestSucceeded` ska vara `True`

## Test på serverdatorn

Kör detta på serverdatorn:

```powershell
curl.exe -i http://127.0.0.1:8080/health
curl.exe -i http://10.156.64.136:8080/health
netstat -ano | findstr :8080
```

Bra tecken:

- både `127.0.0.1` och serverns LAN-IP svarar
- `netstat` visar lyssning på:
  - `0.0.0.0:8080`
  - eller `10.156.64.136:8080`

Om bara `127.0.0.1` fungerar:

- servern är inte exponerad mot nätverket ännu

## Om du använder Codex på serverdatorn

Be Codex där att:

1. verifiera att servern svarar på:
   - `GET /health`
   - `POST /v1/audio/transcriptions`
2. säkerställa att servern binder till `0.0.0.0:8080`
3. säkerställa att brandvägg eller lokal policy tillåter TCP `8080`
4. testa att servern kan nås från klient-IP:
   - `10.146.64.49`
5. hålla servern uppe stabilt medan klienten testas

En bra kort briefing till Codex på servern är:

```text
Jag kör en Nellie-klient på 10.146.64.49 som måste nå den här servern på 10.156.64.136:8080.
Servern måste exponera GET /health och POST /v1/audio/transcriptions på ett OpenAI-kompatibelt sätt.
Se till att tjänsten lyssnar på 0.0.0.0:8080 och att TCP 8080 är nåbar från klienten.
Verifiera både lokalt på servern och från nätet.
```

## Viktig notering

Nellie-klienten har redan stöd för Voxtral-status, fallback till Whisper och tydlig UI-status. Det som fortfarande avgör om Voxtral fungerar är att servern verkligen är stabilt nåbar på:

```text
http://10.156.64.136:8080
```
