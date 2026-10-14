export const BOT_USERNAME = "KaeKae_Toad";

// Calibrated Camfrog UIA coordinates
export const CALIBRATED_WINDOW_RECT: [number, number, number, number] = [1273, 0, 2567, 1399];
export const CHAT_WINDOW_RECT: [number, number, number, number] = [1281, 170, 2355, 1160];
export const CHAT_INPUT_RECT: [number, number, number, number] = [1396, 1206, 2497, 1241];
export const CHAT_INPUT_SCREEN_PT: [number, number] = [1536, 1223];
export const USER_LIST_RECT: [number, number, number, number] = [2359, 141, 2559, 1160];
export const TALK_BUTTON_RECT: [number, number, number, number] = [1291, 1169, 1361, 1195];
export const TALK_BUTTON_SCREEN_PT: [number, number] = [1326, 1182];
export const ACTIVE_SPEAKER_RECT: [number, number, number, number] = [1506, 1174, 1548, 1190];

// Economy & Strategy Constants
export const SPIN_FLAT_COST_PAT = 5_000;
export const SPIN_COOLDOWN_SECONDS = 20.2;
export const RANDOM_SPIN_MIN_SECONDS = 60.0;
export const RANDOM_SPIN_MAX_SECONDS = 180.0;
export const JACKPOT_POOL_CAP_PAT = 5_000_000;
export const JACKPOT_HIT_PROBABILITY = 0.0005;
export const LOW_JACKPOT_THRESHOLD_PAT = 1_750_000;

export const BEG_EXPECTED_PAYOUT_PAT = 5_000;
export const BEG_COOLDOWN_SECONDS = 3 * 3600; // 3 hours

export const LOTTO_TICKET_COST_PAT = 1_000;
export const LOTTO_DRAW_SCHEDULE_DESC = "Sundays at 9:00 PM ET";

// Voices
export const EDGE_FEMALE_VOICES: Record<string, string> = {
  "Edge Aria": "en-US-AriaNeural",
  "Edge Ava": "en-US-AvaMultilingualNeural",
  "Edge Jenny": "en-US-JennyNeural",
  "Edge Sonia (UK)": "en-GB-SoniaNeural",
  "Edge Natasha (AU)": "en-AU-NatashaNeural",
};

export const KOKORO_FEMALE_VOICES: Record<string, string> = {
  "Kokoro Default (Test)": "af_heart",
  "Kokoro Heart": "af_heart",
  "Kokoro Bella": "af_bella",
  "Kokoro Sarah": "af_sarah",
  "Kokoro Emma": "bf_emma",
  "Kokoro Sky": "af_sky",
};

export const COQUI_FEMALE_VOICES: Record<string, string> = {
  "Coqui Default (Test Clone)": "default_sample",
  "Coqui Clara": "clara",
  "Coqui Sofia": "sofia",
  "Coqui Daisy": "daisy",
  "Coqui Freya": "freya",
};

// Default Moderation allowed operators
export const DEFAULT_ALLOWED_ADMINS = [
  "KaeKae_Toad",
  "Stonerwayne1000",
  "Stonerwayne",
  "lockspeck",
  "OMGitsMyPHONE",
  "Rosie",
  "nico1ee",
];

// Stat rescue mapping
export const STAT_RESCUE_GEAR_MAP: Record<string, string> = {
  STR: "breaching",
  DEX: "lockpick",
  CON: "painkillers",
  INT: "hacking",
  WIS: "scanner",
  CHA: "badge",
};

// 40+ Unique roasts for !diss
export const UNIQUE_DISS_TEMPLATES: string[] = [
  "{target}, your comeback is still buffering on 1998 dial-up while your confidence arrived on fiber optic.",
  "{target}, if brains were PAT tokens you wouldn't even have enough to trigger a !beg cooldown.",
  "{target}, I've seen sharper takes from the Wheel of Misfortune landing on bankrupt six times in a row.",
  "{target}, your keyboard must be filing for workers' comp after carrying all that nonsense in chat.",
  "{target}, you type like someone who brings a lockpick to a convenience store heist and still trips the alarm.",
  "{target}, even Camfrog's lurkers scrolled past your message just to protect their eyesight.",
  "{target}, your mic presence has the same energy as a lawnmower starting up at 6 AM on a Sunday.",
  "{target}, if charisma were a D&D stat on your !sheet, yours would still be waiting for a reroll.",
  "{target}, you're the reason the casino vault keeps its doors unlocked—they know you'll still whiff the roll.",
  "{target}, I checked your profile in my SQLite database and even the indexes refused to optimize it.",
  "{target}, your chat history reads like a fortune cookie written by a confused goblin.",
  "{target}, I've heard clearer audio coming from a drive-thru speaker during a thunderstorm.",
  "{target}, you bring 'unspent stat points' energy to every conversation in Players__Lounge.",
  "{target}, if wit were currency, you'd be spamming !beg every three hours on the dot.",
  "{target}, even my backup OCR engine squinted at your last line and said 'nah, skip that.'",
  "{target}, you talk like you've got Kingpin's Ring equipped, but you roll like a level 1 decoy.",
  "{target}, the room's IQ goes up by 12 points every time your typing indicator disappears.",
  "{target}, your hot takes need a patch note, a hotfix, and a full server rollback.",
  "{target}, you're proof that autoplay can happen in real life without a brain attached.",
  "{target}, I'd roast you harder, but Camfrog has a strict policy against smoking low-tier loot.",
  "{target}, your vibe is 10% Mastermind and 90% getting caught at Round 1 of the store robbery.",
  "{target}, even VB-Cable tried to mute itself when it heard your name come up.",
  "{target}, you've got the comedic timing of a 180-second random spin landing on a skull.",
  "{target}, if we put your best comebacks in a vault, nobody would bother forming a crew to rob it.",
  "{target}, you're like a human captcha—nobody understands what you're doing here, and everyone wants to skip.",
  "{target}, I ran sentiment analysis on your messages and the database just returned 'bless their heart.'",
  "{target}, your typing style is what happens when autocomplete gives up and walks out.",
  "{target}, you've got champagne confidence on a !beg handout budget.",
  "{target}, even a 4-pixel Camfrog indicator pane has more presence in this room than that last comment.",
  "{target}, if overconfidence paid out PAT, you'd have capped the 5,000,000 jackpot pool by yourself.",
  "{target}, I asked the magic conch about your next message and it told me to hit !shutup.",
  "{target}, your chat game is like buying 1 ticket in !lotto and already planning your retirement speech.",
  "{target}, you're the human equivalent of forgetting to press the Talk button while giving a 5-minute speech.",
  "{target}, I've seen bots from 2004 AIM chatrooms with smoother conversation skills.",
  "{target}, your roasts hit like a foam noodle in an Arena battle royale.",
  "{target}, every time you grab the mic, three lurkers suddenly remember they have laundry to fold.",
  "{target}, your strategy in chat is all gas, no brakes, and zero steering wheel.",
  "{target}, if we auctioned off your best takes in the heist shop, they'd cost 0 PAT and still go unsold.",
  "{target}, you're out here playing 4D chess against yourself and still losing in three moves.",
  "{target}, even my suppression vault said 'please don't dump that in here.'",
];
