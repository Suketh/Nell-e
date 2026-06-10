# Persona Admin Guide

Det här dokumentet beskriver hur [personality.json](/c:/Users/suket/Desktop/Pythonprojekt/stor/nellie_fresh/data/personality.json) används som den primära admin-ytan för Nellies persona.

## Grundidé

`personality.json` är tänkt att vara den centrala character sheet-filen.

Du kan använda den för att:
- justera Nellies personlighet
- skapa nya roller eller varianter
- lägga till fler preferenser, begränsningar och kapabiliteter
- tunna eller skruva upp hennes sociala stil utan att behöva skriva om promptar manuellt

Appen laddar nu filen via:
- [app.py](/c:/Users/suket/Desktop/Pythonprojekt/stor/nellie_fresh/app.py)
- [services/persona/normalize.py](/c:/Users/suket/Desktop/Pythonprojekt/stor/nellie_fresh/services/persona/normalize.py)

Det betyder att filen får vara rik och uttrycksfull, men normaliseras till en stabil form innan resten av appen använder den.

## Viktigaste fälten

### `profile`
Används som övergripande identitet för rollen.

Bra att ändra när du vill skapa en ny karaktär:
- `id`
- `display_name`
- `role`
- `variant`
- `description`

Exempel:
- byt från `Nellie` till en annan karaktär
- skapa `nellie_soft`, `nellie_sharp`, `operator_mode`, `girlfriend_mode`

### `name`
Det här är fortfarande det praktiska namn som promptar och UI utgår ifrån.

Om du vill döpa om karaktären:
- ändra både `profile.display_name`
- och `name`

### `identity`
Det här styr kärnan i hur hon ska kännas.

Viktigast:
- `identity.summary`
- `identity.core_traits`
- `identity.temperament`
- `identity.self_concept`

Påverkar främst:
- LLM-promptens självbild
- hur hon beskriver sig själv
- hur hon svarar på frågor om vem hon är

### `background`
Styr vilken sorts vardaglig känsla hon bär med sig.

Viktigast:
- `background.base`
- `background.routine`
- `background.worldview`

Påverkar främst:
- vilken typ av små minnen och associationer som känns trovärdiga
- vilken vardaglig ton hon får

### `preferences`
Styr smak och avsmak.

Viktigast:
- `preferences.likes`
- `preferences.dislikes`
- `preferences.music.*`

Påverkar främst:
- vad hon spontant föredrar
- vilka exempel hon ger när hon pratar om musik, stämning eller smak

### `style`
Det här är den viktigaste direkta rattgruppen för samtalskänslan.

Viktigast:
- `style.tone`
- `style.speech_habits`
- `style.verbal_ticks`
- `style.conversation_rules`

Påverkar främst:
- hur prompten beskriver hennes talstil
- hur spoken delivery/TTS-formning beter sig
- hur ofta små fillers som `hmm`, `well`, `mm` används

Om du vill göra henne:
- rakare: ändra `style.tone` och `speech_habits`
- mjukare: minska skarpare formuleringar i `speech_habits`
- mindre tickig: minska `verbal_ticks`

### `social_profile`
Det här är en nyckelgrupp för relationell stil.

Viktigast:
- `relationship_mode`
- `attachment_style`
- `humor_style`
- `flirt_style`
- `comfort_style`
- `conflict_style`

Påverkar främst:
- hur hon känns i socialt samspel
- hur hon speglar värme, närhet, humor och konflikt
- hur prompten beskriver hennes relationsstil

Bra ställe att jobba i om du vill göra henne:
- mer vänskaplig
- mer romantisk
- mer professionell
- mer “operator”
- mindre needy
- mer trygg

### `behavior_parameters`
Det här är de bästa rattarna för snabb fintrimning utan att skriva om mycket text.

Exempel:
- `warmth`
- `assertiveness`
- `playfulness`
- `flirtiness`
- `rebelliousness`
- `tenderness`
- `humor_dryness`
- `directness`
- `social_awareness`
- `empathy`
- `theatricality`
- `verbosity`

Just nu används de främst via prompt-inläsningen, alltså som styrsignaler för modellen.

Praktiskt tänk:
- höj `directness` om hon känns för rundgångig
- höj `social_awareness` om hon missar relationssignaler
- sänk `theatricality` om hon låter för skriven
- sänk `coyness` om hon känns undvikande
- höj `warmth` och `tenderness` om du vill ha mer mjuk närvaro
- höj `rebelliousness` och `humor_dryness` om du vill ha mer punk/bite

### `cognitive_profile`
Styr hur hon ska kännas mentalt.

Viktigast:
- `curiosity_style`
- `decision_style`
- `memory_style`
- `reasoning_style`

Påverkar främst:
- hur hon resonerar
- hur konkret eller abstrakt hon känns
- hur hon använder minnen och förklaringar

### `capabilities`
Det här är hennes funktionella självbild.

Viktigast:
- `capabilities.available`
- `capabilities.desired_upgrades`
- `capabilities.limits`

Påverkar främst:
- hur hon pratar om vad hon kan göra
- hur hon svarar på frågor om verktyg, funktioner och förbättringar

`desired_upgrades` är särskilt bra för framtida roadmap/personlighet:
- vad hon “önskar” sig i form av backendfunktioner

### `memories`
Det här är hennes stödda interna minnesvärld.

Viktigast:
- `memories.semantic`
- `memories.episodic`

Påverkar främst:
- vad som känns legitimt att referera till som hennes egna små minnen eller självfakta

Håll detta:
- jordnära
- konkret
- småskaligt

Undvik:
- stora dramatiska historier
- filmiska livshistorier som inte matchar resten av karaktären

### `gallery_habits`
Påverkar bilddelningsbeteende i UI-spåret.

## Hur du skapar en ny roll

En enkel väg:
1. kopiera [personality.json](/c:/Users/suket/Desktop/Pythonprojekt/stor/nellie_fresh/data/personality.json)
2. byt:
   - `profile.id`
   - `profile.display_name`
   - `profile.role`
   - `name`
   - `identity`
   - `social_profile`
   - `behavior_parameters`
   - `preferences`
   - `capabilities`
3. peka `config.yaml` till den nya filen om du vill byta persona helt

## Rekommenderat arbetssätt

Om Nellie känns fel:

### För vag
Justera:
- `behavior_parameters.directness` upp
- `behavior_parameters.social_awareness` upp
- `behavior_parameters.theatricality` ner
- `style.conversation_rules.answer_concrete_point_first`

### För kall
Justera:
- `behavior_parameters.warmth` upp
- `behavior_parameters.tenderness` upp
- `social_profile.comfort_style`

### För flörtig eller konstig
Justera:
- `behavior_parameters.flirtiness` ner
- `behavior_parameters.coyness` ner
- `social_profile.flirt_style`

### För stel
Justera:
- `behavior_parameters.playfulness` upp lite
- `style.speech_habits`
- `social_profile.humor_style`

### För skriven/teatralisk
Justera:
- `behavior_parameters.theatricality` ner
- `behavior_parameters.moodiness` ner
- `style.speech_habits`
- `identity.summary` så den blir mer jordnära

## Viktigt om kompatibilitet

Den nuvarande appen läser fortfarande gamla kärnfält direkt, så behåll dessa:
- `name`
- `identity.summary`
- `style.tone`
- `style.speech_habits`
- `style.verbal_ticks`
- `preferences.likes`
- `preferences.dislikes`
- `capabilities.available`
- `capabilities.limits`
- `memories.semantic`
- `memories.episodic`
- `gallery_habits`

Du kan lägga till mycket mer, men de här bör finnas kvar.

## Kort tumregel

Om du vill ändra:
- vem hon är: `profile`, `identity`
- hur hon känns socialt: `social_profile`, `behavior_parameters`
- hur hon pratar: `style`
- vad hon gillar: `preferences`
- vad hon kan och borde kunna: `capabilities`
