# INSTALL.md — Setup de LUCA

## Prerrequisitos

- Python 3.11 o superior
- Git
- NVIDIA GPU con drivers + CUDA (verificado en RTX 4060 8GB)
- Ollama instalado para servir el modelo local (ver https://ollama.com)

## Paso 1. Clonar el repositorio

```bash
git clone https://github.com/iqueipopg/LUCA.git ~/luca-ai-lab
cd ~/luca-ai-lab
```

## Paso 2. Entorno Python

```bash
cd ~/luca-ai-lab
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Paso 3. Descargar el modelo local (Qwen 2.5 7B)

Con Ollama:

```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
```

Esto ocupa unos 4.7GB de VRAM. Deja margen en tu RTX 4060 para el resto del pipeline.

Para verificar que funciona:

```bash
ollama run qwen2.5:7b-instruct-q4_K_M "Hola, ¿funcionas?"
```

## Paso 4. Configurar acceso a SEC EDGAR

SEC EDGAR es gratuito pero exige identificar al cliente con un User-Agent. Crea un archivo `.env` en la raíz:

```bash
cat > .env <<EOF
SEC_USER_AGENT="Tu Nombre tu.email@icai.comillas.edu"
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M
EOF
```

`.env` debe estar en `.gitignore` (ya lo está por defecto en el scaffold).

## Paso 5. Verificar que todo funciona

```bash
/home/<tu-usuario>/luca-ai-lab/venv/bin/python -c "import pdfplumber, requests, yaml; print('OK')"
ollama list
nvidia-smi
```


## Troubleshooting

**Ollama no responde:** `systemctl --user status ollama` o reinicia con `ollama serve`.

**Qwen OOM en RTX 4060:** baja a `qwen2.5:7b-instruct-q3_K_M` (más cuantizado) o reduce `num_ctx` en las llamadas.

**EDGAR devuelve 429:** has superado el rate limit (10 req/s). Añade `time.sleep(0.15)` entre requests.
