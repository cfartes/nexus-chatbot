# Nexus Atende

Manual da empresa · Administradores e colaboradores

Painel web: https://atende.nexusdataanalytics.tech

## Índice

1. Primeiro acesso, senha e perfis
2. Funções, colaboradores e configuração inicial
3. Rotina de atendimento e indicadores
4. Automação, base de conhecimento e solução de problemas

## 1. Primeiro acesso, senha e perfis

1. Abra o convite recebido por e-mail e defina sua senha com pelo menos 12 caracteres. O link vale por 24 horas.
2. No painel, selecione sua empresa e entre com o e-mail do convite e a senha criada.
3. Para atualizar a senha, clique em **Alterar senha**, informe a atual e confirme a nova.

**Administrador da empresa.** Configura o WhatsApp e a automação, gerencia funções e colaboradores e acompanha as filas da empresa.

**Colaborador.** Pode acompanhar a fila do seu setor e os atendimentos gerais, assumir conversas, responder, transferir ou encerrar os atendimentos sob sua responsabilidade.

Se o convite do colaborador expirar ou não chegar, o administrador da empresa pode usar **Reenviar convite** em **Colaboradores**. Confira também a caixa de spam.

## 2. Funções, colaboradores e configuração inicial

### Organize a equipe

1. Acesse **Funções → Nova função**. Informe o nome do perfil e selecione um setor de atendimento: **Comercial**, **Financeiro**, **Suporte** ou **SAC**. Por exemplo, **Analista de cobrança** no setor **Financeiro**.
2. Acesse **Colaboradores → Novo colaborador**. Informe nome e e-mail, selecione a função no campo **Perfil** e clique em **Enviar convite**.
3. Use **Editar** para alterar os dados, o perfil ou a situação. Ao excluir um colaborador, ele perde o acesso e seus atendimentos atribuídos voltam à fila. Para excluir uma função em uso, altere primeiro o perfil dos colaboradores vinculados.

O nome da função é usado pela equipe. No WhatsApp, o cliente continua escolhendo entre os quatro setores. Alterar o setor de uma função muda a fila disponível para os colaboradores vinculados.

### Conecte o WhatsApp e configure os avisos

1. Vá a **Configurações → WhatsApp**, informe o número da empresa com DDI e DDD e clique em **Salvar telefone**.
2. Clique em **Iniciar pareamento**. No celular da empresa, abra **Aparelhos conectados** no WhatsApp e escaneie o QR Code do painel. Use **Atualizar conexão** para conferir o status.
3. Em **Avisos de atendimento humano**, informe o e-mail da equipe e salve. Deixe o campo vazio para desativar esses avisos coletivos.

## 3. Rotina de atendimento e indicadores

Em **Atendimento**, clique em um card para abrir a fila correspondente. Os totais incluem as conversas das demais páginas da fila.

- **Em espera** — conversas aguardando um atendente. O colaborador vê as do próprio setor e as gerais.
- **Com a IA** — conversas em atendimento automático.
- **Meus atendimentos** — conversas atribuídas à sua conta.
- **Todos atribuídos** — visão do administrador das conversas atribuídas à equipe. Esse total inclui as conversas de **Meus atendimentos**.
- **Encerrados** — histórico de conversas encerradas, disponível para o administrador.

### Atenda uma conversa

1. Abra uma conversa **Em espera** e clique em **Assumir**. Ela passa para **Meus atendimentos**.
2. Digite sua resposta e clique em **Enviar**. Se aparecer **Na fila**, acompanhe o status da mesma mensagem antes de reenviar.
3. Se outro colaborador deve continuar, selecione o destinatário e clique em **Transferir**. O destinatário recebe um e-mail e um aviso no painel.
4. Ao concluir, clique em **Encerrar atendimento**. Uma nova mensagem do contato abre outro atendimento com o mesmo histórico.

Se precisar intervir em uma conversa automática, o administrador pode usar **Pausar IA**. Para voltar ao atendimento automático, use **Devolver à IA**.

### Receba avisos de transferência

O aviso permanece no painel até você fechá-lo no **X** ou abrir a conversa. Para receber avisos do sistema com o painel aberto, clique em **Ativar notificações do sistema** e permita a notificação no navegador.

## 4. Automação, base de conhecimento e solução de problemas

### Ajuste a experiência automática

- **Boas-vindas.** Defina a mensagem inicial para contatos que chegam diretamente pelo WhatsApp.
- **Origens de contato.** Cadastre um produto ou canal e copie seu link de WhatsApp. O link identifica a origem da conversa e evita a saudação padrão.
- **Base de conhecimento.** Adicione textos, arquivos Markdown, TXT, PDF ou DOCX, ou uma página web autorizada. Cada arquivo pode ter até 4 MiB e 40 mil caracteres de texto extraído. Para PDFs escaneados, aplique OCR antes de importar.
- **Testar a IA.** Faça uma pergunta e confira a resposta, o encaminhamento e as fontes recuperadas antes de usar o fluxo com clientes.

Quando alguém pede atendimento humano, o bot apresenta as opções numeradas de **Comercial**, **Financeiro**, **Suporte** e **SAC**. A escolha determina a fila. Se a IA não conseguir resolver a solicitação, a conversa pode ir para a fila humana geral.

### Dúvidas frequentes

- **Minha fonte não aparece.** Aguarde a etapa de indexação. Se houver falha, leia o aviso no próprio cartão. Divida documentos que ultrapassem o limite de texto.
- **A fila está vazia para um colaborador.** Confirme o setor da função vinculada e confira se ele está na fila correta.
- **A resposta aparece como Na fila.** O painel ainda aguarda o envio ao WhatsApp. Se houver aviso de limite, aguarde o prazo mostrado e confira o status depois.
- **O WhatsApp não conecta.** Confira o número salvo e a sessão no celular da empresa. Se o cartão apresentar um erro, encaminhe a mensagem ao suporte da Nexus.
