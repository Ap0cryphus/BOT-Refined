import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device_map="cpu",
    dtype=torch.float32,
)

wavs, sr = model.generate_custom_voice(
    text="Hello world, this is a test of Qwen3 TTS.",
    language="English",
    speaker="Vivian"
)
sf.write("test.wav", wavs[0], sr)
print("Done!")
