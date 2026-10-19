# Robô de ofertas de eletrodomésticos

Busca ofertas de eletrodomésticos na **Shopee** e no **Mercado Livre**, descarta descontos falsos com base no histórico de preços e posta sozinho:

| Onde | Como |
|---|---|
| **Canal do Telegram** | Uma oferta a cada 20 min, das 8h às 23h |
| **Grupo do WhatsApp** | 6 ofertas por dia, que já saíram no Telegram há pelo menos 1h, com convite para o Telegram no fim |
| **Vídeos** | Às 7h, 12h e 19h o bot manda um vídeo para você aprovar no Telegram |
| **Instagram Reels / YouTube Shorts** | Postados sozinhos quando você aprova o vídeo |
| **TikTok** | Depois da aprovação o bot entrega o vídeo e a legenda; você posta em 1 minuto com um som em alta |

Tudo é configurado no arquivo `.env`, feito a partir do modelo [`.env.example`](.env.example).

---

## 1. Chaves e contas

Só **Telegram + Shopee** já bastam para ligar o robô. O resto pode ser adicionado depois.

### Telegram (obrigatório)
1. Fale com o **@BotFather** → `/newbot` → copie o token para `TELEGRAM_TOKEN`.
2. No seu canal: **Administradores → Adicionar administrador** → escolha o bot. Ele precisa da permissão de postar e da de **convidar usuários via link**, que é usada pelo `/convite`.
3. Em `TELEGRAM_CANAL`, coloque o `@nome` do canal.
4. Depois que o robô estiver no ar, mande `/id` para o bot e copie o número para `TELEGRAM_ADMIN_ID`. Sem isso, o bot não sabe para quem mandar os vídeos.

### Shopee Afiliados
1. Entre em [affiliate.shopee.com.br](https://affiliate.shopee.com.br) → menu **Open API** → solicite o acesso.
2. Quando for liberado, copie o **AppID** para `SHOPEE_APP_ID` e a **Secret** para `SHOPEE_SECRET`.

Os links que o robô posta já são os seus links de afiliado.

### Mercado Livre
1. Em [developers.mercadolivre.com.br](https://developers.mercadolivre.com.br), crie uma aplicação. Use `https://www.google.com` como **Redirect URI**.
2. Copie o **Client ID** e a **Client Secret** para o `.env`.
3. Abra no navegador, trocando `SEU_CLIENT_ID`:
   `https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=SEU_CLIENT_ID&redirect_uri=https://www.google.com`
4. Autorize. Você vai cair no Google com `?code=TG-...` na barra de endereço. Copie esse código e, no servidor, rode:
   `docker compose run --rm robo python -m ofertas ml-token TG-...`
   Cole o resultado em `ML_REFRESH_TOKEN`.
5. **Link de afiliado:** no painel do Programa de Afiliados, gere um link de qualquer produto e copie tudo o que vem **depois do `?`** para `ML_PARAMETROS_AFILIADO`.

> ⚠️ O Mercado Livre vem restringindo a busca da API para apps novos. Se aparecer *"Mercado Livre recusou a busca (403)"* no log, o robô continua funcionando só com a Shopee. Confira também se o link gerado conta como afiliado: abra um link postado e veja se a venda aparece no painel.

### WhatsApp (só depois de 7 dias de aquecimento do número)
1. Instale a **Evolution API** seguindo a [documentação oficial](https://doc.evolution-api.com), que já traz um `docker-compose` pronto. Pode ser no mesmo servidor.
2. Crie uma instância e leia o QR code com o **WhatsApp Business do número do grupo**.
3. Descubra o id do grupo (termina em `@g.us`) pelo endpoint `GET /group/fetchAllGroups/{instancia}?getParticipants=false`.
4. Preencha `EVOLUTION_URL`, `EVOLUTION_KEY`, `EVOLUTION_INSTANCIA` e `WHATSAPP_GRUPO`, e mude `WHATSAPP_ATIVO=true`.

> ⚠️ A Evolution API não é oficial. Use **só o número dedicado**, nunca o pessoal, e abra o WhatsApp do celular pelo menos uma vez por semana.

### Instagram Reels (opcional)
- Você precisa de uma conta **profissional** ligada a uma **Página do Facebook** e de um app em [developers.facebook.com](https://developers.facebook.com) com as permissões `instagram_basic`, `instagram_content_publish` e `pages_show_list`.
- Para publicar na sua própria conta, o app pode ficar em modo de desenvolvimento.
- Em `INSTAGRAM_ID`, coloque o id da conta do Instagram. Em `INSTAGRAM_TOKEN`, use um token de **Usuário do Sistema** do Gerenciador de Negócios, que não expira. Um token comum de longa duração vence em 60 dias.

### YouTube Shorts (opcional)
1. No [Google Cloud](https://console.cloud.google.com), crie um projeto e ative a **YouTube Data API v3**.
2. Crie uma credencial **OAuth (Aplicativo da Web)** com o redirect `https://developers.google.com/oauthplayground`.
3. No [OAuth Playground](https://developers.google.com/oauthplayground), clique na engrenagem, marque *Use your own OAuth credentials*, autorize o escopo `https://www.googleapis.com/auth/youtube.upload` e troque o código pelo **refresh token**.

> ⚠️ Enquanto o projeto não passar pela auditoria gratuita do Google, os vídeos enviados pela API ficam **privados**. Peça a auditoria no formulário da YouTube API Services. Até lá, deixe `YOUTUBE_PRIVACIDADE=private` e publique pelo app do YouTube, ou deixe o YouTube desligado.

---

## 2. Instalar no servidor

Funciona em qualquer VPS com Linux, como o plano gratuito da Oracle Cloud ou opções de uns R$ 25/mês.

```bash
# 1. Instale o Docker
curl -fsSL https://get.docker.com | sh

# 2. Baixe o projeto
git clone https://github.com/aluizio-kleine/personal_general.git
cd personal_general/bot-ofertas

# 3. Configure
cp .env.example .env
nano .env        # preencha as chaves (Ctrl+O salva, Ctrl+X sai)

# 4. Teste antes de ligar de vez
docker compose build
docker compose run --rm robo python -m ofertas coletar         # mostra as 10 melhores ofertas
docker compose run --rm robo python -m ofertas teste-telegram  # posta 1 oferta no canal

# 5. Ligue (reinicia sozinho se o servidor reiniciar)
docker compose up -d
docker compose logs -f   # acompanhar (Ctrl+C sai, o robô continua rodando)
```

Depois de ligar, mande `/id` para o bot, coloque o número em `TELEGRAM_ADMIN_ID` e reinicie com `docker compose up -d`. Para testar o vídeo na hora, mande `/rodada`.

Para atualizar o robô quando houver mudanças: `git pull && docker compose up -d --build`.

---

## 3. Comandos do bot (só respondem a você)

| Comando | O que faz |
|---|---|
| `/status` | Resumo do dia: ofertas vistas, postagens, vídeos |
| `/rodada` | Gera um vídeo agora, fora dos horários |
| `/convite anuncio-a` | Cria um link de convite do canal com esse nome, para medir de onde vêm os membros |
| `/id` | Mostra o seu chat id |

Nos vídeos, os botões fazem o seguinte:
- **✅ Aprovar:** publica no Reels e no Shorts, garante que a oferta está no canal e manda a legenda para o TikTok.
- **❌ Rejeitar:** descarta o vídeo.
- **🔄 Trocar oferta:** gera outro vídeo com a próxima melhor oferta.

---

## 4. Página de destino para os anúncios

O arquivo [`landing/index.html`](landing/index.html) é a página para onde os anúncios levam.

1. Crie os convites no bot: `/convite anuncio-a`, `/convite anuncio-b`.
2. Cole os links em `CONVITES` no fim do arquivo e coloque o link do grupo do WhatsApp em `WHATSAPP`.
3. Publique de graça: em [app.netlify.com/drop](https://app.netlify.com/drop), arraste a pasta `landing`. Você recebe um endereço `https://...`.
4. Em cada anúncio, use o endereço com a origem no final: `https://seusite.netlify.app/?origem=anuncio-a`.

O Telegram mostra quantas pessoas entraram por cada link de convite. Isso dá o **custo por membro** de cada anúncio.

---

## 5. Ajustes úteis no `.env`

| Variável | Para quê |
|---|---|
| `DESCONTO_MINIMO`, `NOTA_MINIMA`, `PRECO_MINIMO` | Deixar o filtro mais ou menos exigente |
| `PALAVRAS_CHAVE` | Trocar ou acrescentar produtos, separados por vírgula |
| `INTERVALO_TELEGRAM_MIN`, `HORA_INICIO`, `HORA_FIM` | Ritmo e horário de silêncio do canal |
| `RODADAS_VIDEO`, `VIDEOS_POR_RODADA` | Horários e quantidade de vídeos |
| `VOZ_EDGE` ou `ELEVENLABS_KEY` + `ELEVENLABS_VOZ` | Voz da narração |
| `MUSICA_FUNDO` | Música livre de direitos tocando baixinho no fundo |

**Sobre o desconto falso:** o robô guarda o preço de cada produto toda vez que o vê. Quando já existem 3 ou mais dias de histórico, ele só posta se o preço estiver pelo menos `QUEDA_MINIMA_HISTORICO`% abaixo do preço normal. Nos primeiros dias, vale só o desconto informado pela loja.

---

## 6. Limitações conhecidas

- O código foi testado com as APIs **simuladas**: coleta, filtro, postagens, geração de vídeo e botões do bot. As chamadas reais à Shopee, ao Mercado Livre, à Evolution API, ao Instagram e ao YouTube seguem a documentação de cada serviço, mas **só vão ser validadas de verdade com as suas chaves**. Se algo falhar, o erro aparece em `docker compose logs`.
- A voz gratuita usa o serviço de leitura do Microsoft Edge, que não é uma API oficial e pode parar de funcionar. Se isso acontecer, use a ElevenLabs.
- O TikTok não é postado automaticamente, de propósito: alcance com som em alta e risco de bloqueio.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
pytest
```
