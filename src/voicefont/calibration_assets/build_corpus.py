"""Authoring source. Run from repository root to regenerate JSON and checklist."""

import json
from pathlib import Path

CATEGORIES = [
    (
        "phonetic",
        "Sounds in everyday words",
        (
            "Natural word contrasts, vowels and consonants. Keep any distinctions "
            "or mergers that belong to your own accent."
        ),
    ),
    (
        "connected",
        "Connected speech",
        (
            "Link words at your normal pace. There is no need to pronounce every "
            "written letter separately."
        ),
    ),
    (
        "questions",
        "Questions and emphasis",
        "Use meaning to shape the sentence. Capitals indicate a suggested focus, not extra volume.",
    ),
    (
        "range",
        "Comfortable variation",
        (
            "Small, easy changes only. Never strain, shout, whisper forcefully or "
            "push to your limits. Every task here is optional."
        ),
    ),
    (
        "expression",
        "Expression and style pairs",
        (
            "Read the same words with a different intention. Gentle acting is "
            "enough; skip anything uncomfortable."
        ),
    ),
    (
        "conversation",
        "Everyday conversation",
        (
            "Speak as if talking with someone you know. Use the supplied text so "
            "repeated recordings remain comparable."
        ),
    ),
    (
        "consistency",
        "Repeat and consistency",
        (
            "Repeat earlier words without trying to copy a waveform. Comfortable, "
            "ordinary delivery is the goal."
        ),
    ),
]
# text | instruction | dimensions | style. These prompts are original, not borrowed passages.
ROWS = {
    "phonetic": [
        (
            "Please leave the green ticket beside the little blue tin.",
            "Use your ordinary speaking voice.",
            "vowels:kit-fleece",
            "neutral",
        ),
        (
            "The full bowl stood beside a cool pool of water.",
            "Keep your own natural distinction between full and pool.",
            "vowels:foot-goose",
            "neutral",
        ),
        (
            "Sam packed a black bag and caught the last bus home.",
            "Say this as an everyday observation; keep your natural a sounds.",
            "vowels:trap-bath-strut",
            "neutral",
        ),
        (
            "We checked the wet deck before taking the late train.",
            "Read smoothly without stretching the vowels.",
            "vowels:dress-face",
            "neutral",
        ),
        (
            "A small pot of sauce was waiting near the door.",
            "Use the vowel sounds that feel normal in your accent.",
            "vowels:lot-thought",
            "neutral",
        ),
        (
            "The nurse heard a bird while stirring her tea.",
            "Keep or omit r sounds as you naturally would.",
            "vowels:nurse;r:accent-natural",
            "neutral",
        ),
        (
            "The bright kite rose above the quiet lane.",
            "Read with easy movement through the vowel sounds.",
            "diphthongs:price-goat-face",
            "neutral",
        ),
        (
            "Our neighbour found a brown pouch under the chair.",
            "Do not imitate another accent.",
            "diphthongs:mouth;vowels:chair",
            "neutral",
        ),
        (
            "Roy enjoyed the noise of coins dropping into the tray.",
            "Keep a conversational pace.",
            "diphthongs:choice",
            "neutral",
        ),
        (
            "Pat bought a pale blue boat for the pond.",
            "Let p and b sounds stay clear without overdoing them.",
            "consonants:p-b",
            "neutral",
        ),
        (
            "Take the tiny dish to the desk by the gate.",
            "Use a relaxed voice and ordinary consonants.",
            "consonants:t-d;k-g",
            "neutral",
        ),
        (
            "Five fresh flowers filled the vase by the window.",
            "Do not force breath through the f and v sounds.",
            "consonants:f-v",
            "neutral",
        ),
        (
            "I think those three paths lead to the other side.",
            "Use your natural pronunciation of th.",
            "consonants:th-voiced-unvoiced",
            "neutral",
        ),
        (
            "Sue chose a soft cushion with a silver zip.",
            "Read naturally rather than as a tongue twister.",
            "consonants:s-z;sh-ch",
            "neutral",
        ),
        (
            "The usual measure of jam is a generous spoonful.",
            "Keep the middle sounds in usual and measure relaxed.",
            "consonants:zh-j",
            "neutral",
        ),
        (
            "Lily rarely leaves her red umbrella in the hall.",
            "Keep your own r and l sounds; no imitation.",
            "consonants:l-r;h",
            "neutral",
        ),
        (
            "Mum hung the linen near the warm landing.",
            "Read gently at an everyday volume.",
            "consonants:m-n-ng",
            "neutral",
        ),
        (
            "We watched the quick young waiter carry the tray.",
            "Let the words flow at your usual pace.",
            "consonants:w-y;clusters",
            "neutral",
        ),
        (
            "The crisp toast slipped from the plate onto the cloth.",
            "Keep the clusters natural; do not exaggerate final sounds.",
            "clusters:initial-final",
            "neutral",
        ),
        (
            "A careful photographer noticed a colourful butterfly.",
            "Allow unstressed syllables to become lighter naturally.",
            "schwa;word-stress",
            "neutral",
        ),
    ],
    "connected": [
        (
            "Could you put it on the table when you have a moment?",
            "Read as one polite request, with natural linking.",
            "linking;weak-forms",
            "neutral",
        ),
        (
            "I would have called, but the train went through a tunnel.",
            "Use the contractions or reductions that occur naturally while reading.",
            "weak-forms;phrase-boundaries",
            "neutral",
        ),
        (
            "We are going to pick up a few things on the way back.",
            "Use a normal conversational rhythm.",
            "reduction;linking",
            "neutral",
        ),
        (
            "The bread and butter are in the bag next to the kettle.",
            "Let small connecting words stay light.",
            "weak-forms:and-the-to",
            "neutral",
        ),
        (
            "First we checked the address, then we rang the bell.",
            "Take an easy pause at the comma.",
            "boundary;clusters",
            "neutral",
        ),
        (
            "I left an orange and a note on the kitchen counter.",
            "Link adjacent words however your accent normally does.",
            "vowel-linking",
            "neutral",
        ),
        (
            "When the rain stopped, everyone stepped outside for a look.",
            "Avoid separating every word.",
            "assimilation;rhythm",
            "neutral",
        ),
        (
            "It is a bit of a walk, but there is a bench halfway.",
            "Read as a reassuring comment to a friend.",
            "weak-forms;rhythm",
            "neutral",
        ),
        (
            "The parcel should arrive at about a quarter past ten.",
            "Use an ordinary pace and natural t sounds.",
            "connected-t;weak-forms",
            "neutral",
        ),
        (
            "If you need anything else, I will be just across the road.",
            "Keep the conditional phrase connected and pause where comfortable.",
            "phrasing;linking",
            "neutral",
        ),
    ],
    "questions": [
        (
            "Did you leave the window open?",
            "Ask a genuine yes-or-no question, not an accusation.",
            "question:yes-no",
            "neutral",
        ),
        (
            "Where did you put the spare key?",
            "Ask as if you genuinely need the information.",
            "question:wh",
            "neutral",
        ),
        (
            "Would you prefer tea, coffee, or a glass of water?",
            "Offer three choices with natural list intonation.",
            "question:choice;list",
            "neutral",
        ),
        (
            "You have already booked the tickets, have you?",
            "Sound mildly curious. Use the question tune natural to you.",
            "question:tag",
            "curious",
        ),
        (
            "I thought you meant the small box.",
            "Emphasise I: someone else understood differently.",
            "stress:subject",
            "neutral",
        ),
        (
            "I thought you meant the small box.",
            "Emphasise small: the size was the misunderstanding.",
            "stress:adjective",
            "neutral",
        ),
        (
            "We can meet on Friday if that suits you.",
            "Emphasise Friday to suggest a different day.",
            "stress:time",
            "neutral",
        ),
        (
            "We can meet on Friday if that suits you.",
            "Make the invitation sound open and flexible, not insistent.",
            "stress:deemphasis",
            "warm",
        ),
    ],
    "range": [
        (
            "The path curves gently round the garden.",
            "Use your normal comfortable pitch as a reference.",
            "pitch:baseline",
            "neutral",
        ),
        (
            "The path curves gently round the garden.",
            "Use a slightly lower comfortable speaking pitch. Do not force it.",
            "pitch:lower-comfortable",
            "low",
        ),
        (
            "The path curves gently round the garden.",
            "Use a slightly higher comfortable speaking pitch. No falsetto is needed.",
            "pitch:higher-comfortable",
            "high",
        ),
        (
            "I will put the clean cups on the shelf.",
            "Speak softly but with voice, not a whisper. Skip if effortful.",
            "volume:soft",
            "soft",
        ),
        (
            "I will put the clean cups on the shelf.",
            "Use your normal indoor speaking volume.",
            "volume:baseline",
            "neutral",
        ),
        (
            "I will put the clean cups on the shelf.",
            "Project a little as if to someone across a small room. Do not shout.",
            "volume:projected-comfortable",
            "projected",
        ),
        (
            "We have time to check the map before we leave.",
            "Speak a little slower than usual, keeping an easy rhythm.",
            "rate:slow",
            "slow",
        ),
        (
            "We have time to check the map before we leave.",
            "Use your ordinary speaking pace.",
            "rate:baseline",
            "neutral",
        ),
        (
            "We have time to check the map before we leave.",
            "Speak a little faster if comfortable. Clear speech matters more than speed.",
            "rate:brisk",
            "brisk",
        ),
    ],
    "expression": [
        (
            "There is a seat for you by the window.",
            "Read plainly as factual information.",
            "pair:seat;emotion:neutral",
            "neutral",
        ),
        (
            "There is a seat for you by the window.",
            "Sound gently welcoming, as if greeting a friend.",
            "pair:seat;emotion:warm",
            "warm",
        ),
        (
            "The little plant has grown a new leaf.",
            "Read as a simple everyday observation.",
            "pair:plant;emotion:neutral",
            "neutral",
        ),
        (
            "The little plant has grown a new leaf.",
            "Let a little pleasure show. A small change is enough.",
            "pair:plant;emotion:pleased",
            "pleased",
        ),
        (
            "We can try the other route in the morning.",
            "Read plainly, without trying to persuade.",
            "pair:route;emotion:neutral",
            "neutral",
        ),
        (
            "We can try the other route in the morning.",
            "Sound calmly reassuring, not forceful.",
            "pair:route;emotion:reassuring",
            "reassuring",
        ),
        (
            "I did not expect to find a letter in the box.",
            "Give the information matter-of-factly.",
            "pair:letter;emotion:neutral",
            "neutral",
        ),
        (
            "I did not expect to find a letter in the box.",
            "Add gentle surprise without gasping or raising your voice.",
            "pair:letter;emotion:surprised",
            "surprised",
        ),
        (
            "The meeting will begin after the short break.",
            "Read like a clear, calm announcement.",
            "pair:meeting;style:formal",
            "formal",
        ),
        (
            "The meeting will begin after the short break.",
            "Say it casually to a colleague beside you.",
            "pair:meeting;style:casual",
            "casual",
        ),
        (
            "The lid is still stuck, so I will leave it for now.",
            "Read as neutral information.",
            "pair:lid;emotion:neutral",
            "neutral",
        ),
        (
            "The lid is still stuck, so I will leave it for now.",
            "Suggest mild frustration with timing, not strain or loudness.",
            "pair:lid;emotion:frustrated",
            "frustrated",
        ),
    ],
    "conversation": [
        (
            "Hello, it is good to hear from you. How has your week been?",
            "Speak as if starting a relaxed phone call.",
            "greeting;turn-taking",
            "warm",
        ),
        (
            "Yes, that works for me. Shall I bring something for lunch?",
            "Imagine replying to a friendly invitation.",
            "response;follow-up",
            "casual",
        ),
        (
            "Sorry, I missed the last part. Could you say the time again?",
            "Make a polite request for clarification.",
            "repair;question",
            "casual",
        ),
        (
            "Let me think for a moment. I believe we turned left after the bridge.",
            "Allow a short, natural thinking pause between sentences.",
            "hesitation;recollection",
            "neutral",
        ),
        (
            "Thanks for waiting. The kettle took a little longer than I expected.",
            "Speak as if returning with a cup of tea.",
            "thanks;explanation",
            "warm",
        ),
        (
            "I see what you mean, although I would probably choose the smaller one.",
            "Disagree gently at a normal volume.",
            "disagreement;contrast",
            "casual",
        ),
        (
            "For the soup, chop the carrot first. Then add it to the pan and stir slowly.",
            "Explain these steps clearly to one listener.",
            "instruction;sequence",
            "neutral",
        ),
        (
            "The address is twenty-four Willow Lane, and the appointment is at half past two.",
            "Read the numbers and time clearly, without exaggerated spacing.",
            "numbers;time;information",
            "neutral",
        ),
        (
            "I looked for the book upstairs. In the end, it was under the chair all along.",
            "Tell this tiny story with an easy pause between sentences.",
            "narrative;phrasing",
            "casual",
        ),
        (
            "That is everything for today. Take care, and I will speak to you soon.",
            "Close a conversation naturally.",
            "farewell;turn-ending",
            "warm",
        ),
    ],
    "consistency": [
        (
            "Please leave the green ticket beside the little blue tin.",
            (
                "Repeat the first prompt in your ordinary voice. Do not try to imitate "
                "the earlier recording."
            ),
            "repeat:phonetic-01;consistency",
            "neutral",
        ),
        (
            "Could you put it on the table when you have a moment?",
            "Repeat the earlier request at your comfortable normal pace.",
            "repeat:connected-01;consistency",
            "neutral",
        ),
        (
            "Did you leave the window open?",
            "Ask the same genuine question again, without exaggeration.",
            "repeat:questions-01;consistency",
            "neutral",
        ),
        (
            "The path curves gently round the garden.",
            "Return to your normal pitch after the optional variations.",
            "repeat:range-01;baseline-return",
            "neutral",
        ),
        (
            "There is a seat for you by the window.",
            "Use plain neutral delivery again, after the expression pairs.",
            "repeat:expression-01;baseline-return",
            "neutral",
        ),
        (
            "Please leave the green ticket beside the little blue tin.",
            "Take a comfortable pause first, then give one final natural reading.",
            "repeat:phonetic-01;session-end",
            "neutral",
        ),
    ],
}


def build():
    corpus = {
        "version": "1.0.0",
        "language": "en-GB",
        "title": "VoiceFont Calibration Checklist",
        "disclaimer": (
            "Use your own natural accent, not an imitation. These original prompts "
            "sample everyday sounds and delivery choices; they cannot capture "
            "every facet of a voice and do not test identity, emotion or "
            "pronunciation. Stay within a comfortable speaking range, take breaks "
            "and skip any task that feels uncomfortable. Record only your own "
            "voice or one you have explicit permission to use."
        ),
        "categories": [
            dict(id=id_, title=title, description=description)
            for id_, title, description in CATEGORIES
        ],
        "prompts": [],
    }
    for category, rows in ROWS.items():
        for index, (text, instruction, dimensions, style) in enumerate(rows, 1):
            corpus["prompts"].append(
                dict(
                    id=f"{category}-{index:02d}",
                    category=category,
                    text=text,
                    instruction=instruction,
                    dimensions=dimensions.split(";"),
                    optional=category in ("range", "expression"),
                    style=style,
                )
            )
    return corpus


if __name__ == "__main__":
    from voicefont.corpus import render_checklist, validate_corpus

    corpus = build()
    validate_corpus(corpus)
    here = Path(__file__).resolve().parent
    (here / "corpus.json").write_text(
        json.dumps(corpus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    root = here.parents[2]
    (root / "docs" / "Calibration Checklist.md").write_text(
        render_checklist(corpus), encoding="utf-8"
    )
    print(f"Generated {len(corpus['prompts'])} prompts and matching checklist")
