import { BOT_USERNAME, UNIQUE_DISS_TEMPLATES } from "./constants";
import { UserProfile, ModerationEvent } from "../types";

const WORD_RE = /[A-Za-z][A-Za-z'-]{2,}/g;

const NON_NOUN_STOPWORDS = new Set([
  "the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were", "have", "has",
  "had", "not", "but", "what", "all", "can", "her", "his", "him", "she", "they", "them", "their",
  "from", "out", "about", "who", "get", "got", "just", "like", "know", "how", "when", "where",
  "why", "would", "could", "should", "will", "there", "here", "been", "into", "more", "some",
  "than", "then", "now", "only", "also", "very", "too", "much", "many", "well", "back", "even",
  "still", "way", "our", "one", "two", "see", "saw", "did", "does", "doing", "done", "make",
  "made", "take", "took", "come", "came", "going", "went", "want", "said", "say", "says",
  "really", "right", "yeah", "yes", "nah", "nope", "lol", "lmao", "rofl", "omg", "wtf", "idk",
  "dont", "don't", "cant", "can't", "im", "i'm", "ive", "i've", "its", "it's", "youre", "you're",
  "thats", "that's", "whats", "what's", "let", "lets", "hey", "hello", "good", "great", "nice",
  "cool", "sure", "okay", "never", "always", "every", "other", "another", "same", "such",
  "over", "under", "again", "after", "before", "because", "while", "through", "between",
]);

const POSITIVE_WORDS = new Set([
  "love", "great", "awesome", "amazing", "good", "nice", "happy", "win", "won", "jackpot",
  "sweet", "cool", "best", "thanks", "thank", "haha", "lol", "lmao", "fun", "glad", "fire",
  "goat", "legend", "blessed", "boom", "congrats", "hella", "lit",
]);

const NEGATIVE_WORDS = new Set([
  "hate", "bad", "mad", "angry", "sad", "lost", "lose", "bust", "busted", "stupid", "dumb",
  "trash", "rigged", "annoying", "wtf", "damn", "sucks", "worst", "broke", "ugly", "fake",
  "boring", "tired", "sick", "cry",
]);

export function analyzeSentimentAndTone(text: string): { score: number; tone: string } {
  const matches = (text || "").match(WORD_RE) || [];
  const words = matches.map((w) => w.toLowerCase());
  if (words.length === 0) return { score: 0.0, tone: "neutral" };

  let pos = 0;
  let neg = 0;
  for (const w of words) {
    if (POSITIVE_WORDS.has(w)) pos++;
    if (NEGATIVE_WORDS.has(w)) neg++;
  }

  const exclam = (text.match(/!/g) || []).length;
  const quest = (text.match(/\?/g) || []).length;
  const score = Number(((pos - neg) / Math.max(1, pos + neg + 1)).toFixed(3));

  let tone = "conversational/chill";
  if (score >= 0.25) {
    tone = exclam === 0 ? "upbeat/positive" : "excited/hyped";
  } else if (score <= -0.25) {
    tone = exclam === 0 ? "salty/critical" : "heated/fiery";
  } else if (quest >= 1) {
    tone = "inquisitive/curious";
  } else if (exclam >= 2) {
    tone = "energetic/expressive";
  }

  return { score, tone };
}

export function extractTopNoun(texts: string[]): { noun: string; count: number } {
  const counts: Record<string, number> = {};
  for (const raw of texts) {
    const cleaned = (raw || "").replace(/^\[MIC\]\s*/i, "");
    if (cleaned.startsWith("!")) continue;
    const matches = cleaned.match(WORD_RE) || [];
    for (const word of matches) {
      const low = word.toLowerCase();
      if (low.length < 3 || NON_NOUN_STOPWORDS.has(low) || low === BOT_USERNAME.toLowerCase()) {
        continue;
      }
      counts[low] = (counts[low] || 0) + 1;
    }
  }

  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return { noun: "n/a", count: 0 };
  }
  entries.sort((a, b) => b[1] - a[1]);
  return { noun: entries[0][0], count: entries[0][1] };
}

export function detectModeration(text: string): { actor: string; target: string; action: ModerationEvent["action"] } | null {
  const t = text.trim();
  const byMatch = t.match(/^([A-Za-z0-9_$.\-[\]@~^]{2,32})\s+was\s+(unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+by\s+([A-Za-z0-9_$.\-[\]@~^]{2,32})/i);
  if (byMatch) {
    return {
      target: byMatch[1],
      action: byMatch[2].toLowerCase() as ModerationEvent["action"],
      actor: byMatch[3],
    };
  }

  const directMatch = t.match(/^([A-Za-z0-9_$.\-[\]@~^]{2,32})\s+(unpunished|unblocked|unbanned|punished|blocked|banned|kicked)\s+([A-Za-z0-9_$.\-[\]@~^]{2,32})/i);
  if (directMatch) {
    return {
      actor: directMatch[1],
      action: directMatch[2].toLowerCase() as ModerationEvent["action"],
      target: directMatch[3],
    };
  }

  return null;
}

export class KaeKaeBrain {
  private usedDisses = new Set<string>();

  applyTone(message: string, tone: string, chatMode: boolean): string {
    if (!chatMode) return message;
    if (tone === "happy") return `✨😊 ${message} 💖`;
    if (tone === "sad") return `🌧️😔 *sigh*... ${message} 💔`;
    if (tone === "mad") return `🔥😤 LISTEN UP: ${message} 💢`;
    return message;
  }

  pickUniqueDiss(target: string, profile?: UserProfile): string {
    const available = UNIQUE_DISS_TEMPLATES.filter((t) => !this.usedDisses.has(t));
    if (available.length === 0) {
      const noun = profile?.top_noun || "keyboard";
      const msgs = profile?.message_count || this.usedDisses.size;
      const dynamic = `${target}, Roast #${this.usedDisses.size + 1}: after ${msgs} messages and obsessing over '${noun}', your banter still couldn't pass a Round 1 store heist check.`;
      this.usedDisses.add(dynamic);
      return dynamic;
    }
    const chosen = available[Math.floor(Math.random() * available.length)];
    this.usedDisses.add(chosen);
    return chosen.replace("{target}", target);
  }

  generateContextualReply(
    sender: string,
    text: string,
    profile: UserProfile | undefined,
    recentMessages: { sender: string; text: string }[],
    currentSpeaker: string | null,
    tone: string,
    chatMode: boolean
  ): string {
    const cleanedPrompt = text.replace(/\bkaekae(?:_toad)?\b[\s,:!-]*\s*/i, "").trim();

    const userGender = profile?.gender || "unknown";
    const userMsgs = profile?.message_count || 1;
    const chatMins = Math.round((profile?.total_chat_seconds || 0) / 60);
    const userTone = profile?.text_tone || "chill";
    const userNoun = profile?.top_noun || "lounge";
    const activeMic = currentSpeaker || "None (Mic Free)";
    const micGrabs = profile?.mic_grab_count || 0;
    const micTranscript = profile?.mic_transcripts?.[0] ? `"${profile.mic_transcripts[0].slice(0, 45)}"` : "";

    const lowQ = (cleanedPrompt || text).toLowerCase();
    const isQuestion = text.includes("?") || /^(what|who|where|when|why|how|are|is|do|does|can|will|should|did|tell|gimme|give)\b/.test(lowQ);

    let base = "";
    if (isQuestion) {
      if (lowQ.includes("how are you") || lowQ.includes("whats up") || lowQ.includes("what's up")) {
        base = `@${sender}, I'm locked in watching the room (active mic: ${activeMic}). You've dropped ${userMsgs} messages in ${chatMins}m with that signature ${userTone} style!`;
      } else if (lowQ.includes("who is on mic") || lowQ.includes("who's on mic") || lowQ.includes("speaker")) {
        base = `@${sender}, radar sweep on Active Speaker: ${activeMic}!`;
      } else if (lowQ.includes("who am i") || lowQ.includes("my info") || lowQ.includes("what do you know")) {
        const micPart = micGrabs > 0 ? `, plus ${micGrabs} mic grabs` : "";
        base = `@${sender}, my compartmentalized memory has you pegged: ${userGender}, ${userMsgs} chat lines${micPart}, favorite noun '${userNoun}', and a distinctly ${userTone} energy!`;
      } else if (lowQ.includes("roast me") || lowQ.includes("diss me")) {
        base = `@${sender}, ` + this.pickUniqueDiss(sender, profile);
      } else {
        const wittySpices = [
          `With your ${userTone} take on '${userNoun}', my tactical answer is: bet on the numbers, watch the cooldown clock, and stay ahead of the curve.`,
          `Cross-referencing your ${userMsgs} messages and '${userNoun}' focus: the answer is a firm YES, but keep 5,000 PAT ready.`,
          `Looking at how the lounge is moving right now: your question cuts straight to the core. Tactical green light!`,
        ];
        const hashIdx = Math.abs((sender + text).split("").reduce((acc, c) => acc + c.charCodeAt(0), 0)) % wittySpices.length;
        base = `@${sender}, ${wittySpices[hashIdx]} (Caught: ${(cleanedPrompt || text).slice(0, 75)})`;
      }
    } else {
      const micTease = micTranscript ? ` (still remember when you said ${micTranscript} on mic)` : "";
      const wittyComebacks = [
        `@${sender}, heard loud and clear! Tracking your ${userMsgs} lines and that ${userTone} vibe${micTease}: '${(cleanedPrompt || text).slice(0, 90)}'`,
        `@${sender}, you always bring that energy to '${userNoun}'—I'm all ears on: '${(cleanedPrompt || text).slice(0, 90)}'`,
        `@${sender}, logged straight into my neural memory banks! Context says we're rolling with it.`,
      ];
      const hashIdx = Math.abs((sender + text).split("").reduce((acc, c) => acc + c.charCodeAt(0), 0)) % wittyComebacks.length;
      base = wittyComebacks[hashIdx];
    }

    return this.applyTone(base, tone, chatMode);
  }

  generateIdkReply(sender: string, question: string, profile: UserProfile | undefined, tone: string, chatMode: boolean): string {
    const q = question.trim();
    if (!q) {
      return this.applyTone(`@${sender}, give me a question after !idk and I'll drop the knowledge.`, tone, chatMode);
    }

    const low = q.toLowerCase();
    const favNoun = profile?.top_noun || "chat";

    // Quick arithmetic evaluator
    const mathMatch = low.match(/(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)/);
    if (mathMatch) {
      const a = parseFloat(mathMatch[1]);
      const op = mathMatch[2];
      const b = parseFloat(mathMatch[3]);
      const res = op === "+" ? a + b : op === "-" ? a - b : op === "*" ? a * b : b !== 0 ? a / b : 0;
      return this.applyTone(`@${sender}, quick math says ${res}—faster than a 20.2s wheel spin.`, tone, chatMode);
    }

    let ans = "";
    if (low.includes("jackpot") || low.includes("spin") || low.includes("pat")) {
      ans = `@${sender}, every !spin costs 5,000 PAT with a 20s cooldown, feeds the 5,000,000 PAT Golden Jackpot, and triggers Pity Surge after 6 losses!`;
    } else if (low.includes("heist") || low.includes("bail") || low.includes("vault")) {
      ans = `@${sender}, INT 18 + DEX 16 + CON 15 is the strongest Mastermind build—and !bail before the vault door saves your loot +20%!`;
    } else if (low.startsWith("why ") || low.startsWith("how come")) {
      ans = `@${sender}, because in Players__Lounge chaos is a feature, not a bug (and your top noun '${favNoun}' proves it) regarding: ${q.slice(0, 110)}`;
    } else if (low.startsWith("when ") || low.startsWith("what time")) {
      ans = `@${sender}, right after the next wheel cooldown—or whenever '${favNoun}' stops trending in chat: ${q.slice(0, 110)}`;
    } else {
      const wittyPool = [
        `@${sender}, smart money says: trust the math, keep 5,000 PAT in reserve, and never bet against KaeKae_Toad on '${q.slice(0, 100)}'.`,
        `@${sender}, I cross-checked the chat history and your '${favNoun}' habit—the verdict on '${q.slice(0, 100)}' is 100% certified facts.`,
        `@${sender}, even the Crowned Gambling Frog knows the answer to '${q.slice(0, 100)}' is to play it cool and collect the payout.`,
      ];
      const hashIdx = Math.abs(q.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0)) % wittyPool.length;
      ans = wittyPool[hashIdx];
    }

    return this.applyTone(ans, tone, chatMode);
  }
}
