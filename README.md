SDK - CPQD Transcrição de Diálogos
==================================

O kit de desenvolvimento para o CPQD Transcrição de Diálogos visa
facilitar a integração do transcritor em aplicações em Python. Ele
é uma alternativa à [API REST](https://speechweb.cpqd.com.br/trd/docs/latest/)
oficial, com as seguintes facilidades implementadas:

 - Encapsulamento da API REST com a biblioteca `requests`
 - Transcrição por arquivos com resultado síncrono ou via _callback_

O SDK utiliza a biblioteca [gevent](http://www.gevent.org/) e seu servidor WSGI
para as chamadas de callback via Webhooks.

## Requisitos e instalação

Testado com Python 3.7. Para dependências, ver _requirements.txt_.
Para instalação automática do SDK e dependências via `pip`, execute a linha abaixo:

```shell
$ pip install git+https://github.com/CPqD/trd-sdk-python.git@v1.0.0
```

#### Servidor WSGI para _callbacks_ via Webhooks

O SDK possui um servidor WSGI interno que precisa de exposição de porta para o correto
funcionamento. Para isso, é necessária a configuração da porta de saída do cliente,
habilitando a porta em quaisquer _firewalls_ e realizando o _port forwarding_ em _gateways_
entre a máquina do cliente e a WAN. O trabalho é equivalente a prover um servidor HTTP
simples para acesso externo.

## Exemplos de uso

#### Inicialização do cliente:

```python
from cpqdtrd import TranscriptionClient

client = TranscriptionClient(
    api_url="https://speech.cpqd.com.br/trd/v3",
    webhook_port=443, # Outbound, precisa de redirecionamento para a WAN
    webhook_host="100.100.100.100", # IP externo ou DNS
    webhook_listener='0.0.0.0',
    webhook_protocol="https",
    username="<username>",
    password="<password>"
    )
```

#### Operação de transcrição simples:

```python
job_id, result = client.transcribe("/caminho/para/audio.wav")
```

Alternativamente, o usuário pode escolher apenas iniciar a transcrição
e esperar pelo resultado posteriormente usando um valor negativo para o
parâmetro de timeout:

```python
job_id = client.transcribe("/caminho/para/audio.wav", timeout=-1)
result = client.wait_result(job_id)
```

As operações `transcribe` com `timeout>=0` e `wait_result` por padrão deletam o
arquivo após o término da transcrição (`delete_after=True`).

#### Impressão de resultado via _callback_:

```python
def callback(job_id, response):
    print(job_id, response)

client.register_callback(callback)
job_id, result = client.transcribe("/caminho/para/audio.wav")
```

É possível melhorar o controle de resultado usando uma classe de contexto para
armazenar os resultados para uso fora da _callback_.

```python
class Context():
    def __init__(self):
        self.results = {}

    def callback(self, job_id, response):
        job = response["job"]
        if job["status"] == "COMPLETED":
            job_id = job["id"]
            segments = response["segments"]
            self.results[job_id] = {
                "job": job,
                "segments": segments}


c = Context()
client.register_callback(c.callback)
job_id, result = client.transcribe("example.wav")
print(c.result)
```

A operação `transcribe` síncrona, assim como a operação `wait_result` esperam pela
execução de todos os _callbacks_.

#### Transcrição de grande volume de arquivos e análise de progresso:

Utilizando a transcrição não-bloqueante, é possível iniciar a transcrição de
vários arquivos em sequência, sem a necessidade de esperar o término de
transcrições anteriores. Na implementação a seguir, usamos a biblioteca
`tqdm` para exibir a barra de progresso, e o `RLock` da biblioteca
`gevent` para controle de concorrência.

```python
from gevent.lock import RLock
from glob import glob
import tqdm

to_transcribe = glob("/caminhos/para/audios/*.wav")

class Context:
    def __init__(self):
        self.results = {}
        self.lock = RLock()
        self.pbar = tqdm.tqdm(total=len(to_transcribe))

    def callback(self, job_id, response):
        job = response["job"]
        if job["status"] == "COMPLETED":
            job_id = job["id"]
            segments = response["segments"]
            self.results[job_id] = {
                "job": job,
                "segments": segments}
            with self.lock:
                self.pbar.update(1)

c = Context()
client.register_callback(c.callback)

# Armazena todos os job_ids para esperar os resultados.
job_ids = []
for path in to_transcribe:
    job_ids.append(client.transcribe(path, timeout=-1))
for job_id in job_ids:
    client.wait_result(job_id)
for id in c.results:
    print("id: {}\n\tstatus:{}\n\tfilename:{}\n\tsegments:{}\n".format(
        id,
        c.results[id]["job"]["status"],
        c.results[id]["job"]["filename"],
        c.results[id]["segments"],
        )
    )
```

## Segurança

O SDK também serve de exemplo para uma implementação aderente aos requisitos
de segurança da integração em nuvem com a
[API de Webhook](https://speechweb.cpqd.com.br/trd/docs/2.4/api_rest/api_webhook.html)
do Transcritor de Diálogos do CPQD. Ele implementa de forma transparente ao usuário
as seguintes medidas de segurança:

 - Serviço HTTPs usando o PyWSGI, com registro de certificado e token de validação
   via endpoint `/webhook/validate`
 - Par de chave privada e certificado efêmeros, com tempo de vida restrito à
   instância da classe `TranscriptionClient`
 - Verificação de token em todos os _callbacks_ registrados via método
   `TranscriptionClient.register_callback()`
