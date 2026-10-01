param([string]$Text)

python -c "
import torch, soundfile as sf, sys
from qwen_tts import Qwen3TTSModel
model = Qwen3TTSModel.from_pretrained(
    'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice',
    device_map='cpu',
    dtype=torch.float32,
)
wavs, sr = model.generate_custom_voice(
    text=sys.argv[1],
    language='English',
    speaker='Vivian'
)
sf.write('bot_speak.wav', wavs[0], sr)
" "$Text"

[System.Reflection.Assembly]::LoadWithPartialName("System.Media") | Out-Null
[System.Media.SoundPlayer]::new("bot_speak.wav").PlaySync()
