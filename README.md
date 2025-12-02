# Fuzzy-DC-Control: Sistema Inteligente de Climatização para Data Center

## Overview

Este projeto implementa um Sistema de Controle Fuzzy (Lógica Nebulosa) do tipo PD (Proporcional-Derivativo) para gerenciar a potência de refrigeração de um Data Center.O principal objetivo é simular e manter a temperatura interna do Data Center ($T_n$) no setpoint de $22.0^\circ\text{C}$ ajustando o valor de $\text{PCRAC}$ (Potência do Computer Room Air Conditioning) em tempo real. O sistema interage com o ambiente simulado e com uma interface de monitoramento (Node-RED) através do protocolo MQTT.

<hr>

Funcionalidades Principais
Controle Inteligente: Aplicação de Lógica Fuzzy (Mamdani) para tomada de decisão robusta.

Modelo de Planta: Simulação da inércia térmica e dinâmica de temperatura do Data Center.

Comunicação Assíncrona: Uso de MQTT para desacoplar o controlador da interface e dos fatores de perturbação.

Monitoramento Ativo: Sistema de alertas para condições críticas de temperatura, sobrecarga do CRAC (eficiência) e instabilidade de controle (oscilação).

Interface Web: Dashboard em Node-RED para visualização em tempo real e injeção de perturbações (Carga Térmica e Temperatura Externa).

<hr>

## Configuração e Instalação

O projeto requer Python 3.x e as seguintes dependências.

```bash
pip install numpy scikit-fuzzy paho-mqtt matplotlib
```

#### Execução do Controlador

1. Salve o código principal como fuzzy_miso.py.

2. Inicie a execução:

```bash
python fuzzy_miso.py
```

3. O script se conectará ao broker MQTT e começará a calcular o controle. Para um encerramento limpo (garantindo que a thread MQTT seja parada), use Ctrl+C.

<hr>

## Arquitetura do Sistema

O sistema segue o padrão MISO (Multiple-Input, Single-Output), operando em uma arquitetura de microsserviços leves (Python, MQTT e Node-RED).

1. Controlador Fuzzy
   O controlador utilizado nesse projeto é um sistema Mamdani que recebe duas entradas e calcula uma saída.

| Variável    | Tipo                 | Universo (Alcance) | Descrição                     |
| ----------- | -------------------- | ------------------ | ----------------------------- |
| errotemp    | Antecedente (Input)  | [−16, 16.1] °C     | Erro: Tn − Tsetpoint          |
| varerrotemp | Antecedente (Input)  | [−2, 2.1] °C/loop  | Derivativo: Erro_k − Erro_k−1 |
| pcrac       | Consequente (Output) | [0, 101] %         | Potência de Controle do CRAC  |

2. Funções de Pertinência

As funções de pertinência são usadas para calcular quais conjuntos da entrada (para as funções das variáveis de entrada) e quais regras (para a função de pertinência de saída) estão sendo ativadas dada uma determinada temperatura. É importante que os gráficos dos conjuntos se sobreponham para que o sistema fuzzy funcione corretamente.

Funções de pertinência das variáveis de entrada: considerando os setpoints desejados (16; 22; 25; 32) e que a temperatura varia entre 16 e 32 graus celsius, o erro mínimo e máximo podem ser calculados da seguinte forma:

e_min = T_min - Setpoint_max = 16 - 32 = -16

e_max = T_max - Setpoint_min = 32 - 16 = 16

Para a variação do erro foram considerados os valores mínimo e máximo como -2 e 2, respectivamente. Isso se dá pelo fato de que a variação do erro não pode ser muito abrupta entre as medidas.

Função de pertinência de saída: A potência pode variar entre 0% e 100%. Os triângulos que representam os conjuntos da saída foram divididos igualmente no eixo da potência.

As funções de pertinência triangulares e trapezoidais definem os conjuntos fuzzy das variáveis:
| Variável | Conjuntos Linguísticos  
|-------------|----------------------------------------------------------------------------------|
| errotemp | MN (Muito Negativo), PN (Pouco Negativo), ZE (Zero), PP (Pouco Positivo), MP (Muito Positivo)
| varerrotemp | MN (Muito Negativo), PN (Pouco Negativo), ZE (Zero), PP (Pouco Positivo), MP (Muito Positivo)  
| pcrac | MB (Muito Baixa), B (Baixa), M (Média), A (Alta), MA (Muito Alta)

Gráficos das Funções de Pertinência:

![Gráficos](/imagens/graficos.png)

3. Base de Regras

O controlador utiliza uma matriz de 5x5 com 25 regras, garantindo uma resposta suave e adaptativa. A lógica segue o princípio de que, se a temperatura estiver alta (errotemp = MP) e aumentando (varerrotemp = MP), a potência deve ser máxima (MA).

Para garantir a convergência do sistema, as regras foram escritas de forma que houvessem poucos ou nenhum saltos entre as regras, exemplo de MB para M é um salto.

O erro foi tomado como variável principal, sendo as regras ditadas principalmente por ele, e a variação do erro foi usada para aperfeiçoar o sistema. Percebe-se que quando a temperatura está muito abaixo do setpoint, porém a variação do erro está muito elevada, a saída do sistema é a potência baixa. Essa decisão foi feita poque por mais que a temperatura esteja baixa, houve um aumento de temepratura elevado anteriormente indicado pela variação do erro, portanto não é necessário elevar tanto a potência do sistema de refrigeração.

]
| varerrotemp \ errotemp | MN | PN | ZE | PP | MP |
| ---------------------- | --- | --- | --- | --- | --- |
| MN | MB | MB | B | M | A |
| PN | MB | B | M | A | MA |
| ZE | MB | B | M | A | MA |
| PP | MB | B | M | A | MA |
| MP | B | M | A | MA | MA |

<hr>

## Função de Transferência

O comportamento térmico do Data Center é simulado internamente pelo controlador através de uma equação de diferenças de primeira ordem, que considera a inércia, a ação de controle e as perturbações externas:
$$\mathbf{T_{next}} = (0.9 \cdot T_n) - (0.08 \cdot \text{PCRAC}) + (0.05 \cdot Qest) + (0.02 \cdot Text) + 3.5$$

Onde:

- $T_n$: Temperatura atual.
- $\text{PCRAC}$: Potência de resfriamento (variável de controle, $0-100\%$).
- $Qest$ (cargaTermica): Carga térmica de equipamentos (perturbação, $0-100$).
- $Text$ (temp/externa): Temperatura externa (perturbação, ${}^\circ\text{C}$).
- $0.9$, $-0.08$, $0.05$, $0.02$: Coeficientes de inércia, resfriamento, carga e perturbação externa, respectivamente.
- $3.5$: Constante de aquecimento de base.

<hr>

## Comunicação MQTT

O projeto utiliza o broker público test.mosquitto.org:1883.

#### Tópicos de Entrada e Controle

| Tópico                 | Conteúdo | Descrição                                                       |
| ---------------------- | -------- | --------------------------------------------------------------- |
| entrada/temp/externa   | Float    | Valor da temperatura externa (Text).                            |
| entrada/cargaTermica   | Float    | Valor da carga térmica (Qest).                                  |
| datacenter/fuzzy/reset | Qualquer | Comando para resetar **Text** e **Qest** para valores iniciais. |

#### Tópicos de Saída e Monitoramento

| Tópico                         | Conteúdo   | Descrição                                                        |
| ------------------------------ | ---------- | ---------------------------------------------------------------- |
| datacenter/fuzzy/control       | Float      | A Potência de Controle (PCRAC) calculada.                        |
| datacenter/fuzzy/temp          | Float      | A Temperatura simulada do Data Center (Tnext).                   |
| datacenter/fuzzy/alert         | JSON       | Alertas de sistema (críticos, eficiência, estabilidade).         |
| datacenter/fuzzy/inference     | JSON       | Dados detalhados do ponto de operação e regras ativadas.         |
| datacenter/fuzzy/inference/img | Base64 PNG | Gráfico de inferência fuzzy (funções ativadas e defuzzificação). |
| datacenter/fuzzy/img/rules     | Base64 PNG | Gráfico das Funções de Pertinência (Publicado com Retain).       |

<hr>

## Sistema de Alertas e Monitoramento

O controlador inclui lógica de segurança para alertar sobre condições operacionais indesejadas, publicando no tópico datacenter/fuzzy/alert em formato JSON.

| Tipo de Alerta | Severidade | Condição de Disparo                                                                                                                                  |
| -------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Crítico        | crítica    | Temperatura simulada (Tnext) fora do limite seguro (abaixo de 18 °C ou acima de 26 °C).                                                              |
| Eficiência     | alta       | PCRAC operando acima de 95% por um período prolongado (10 segundos), indicando sobrecarga na planta.                                                 |
| Estabilidade   | média      | Oscilações excessivas: ≥6 mudanças de sinal de erro (positivo ↔ negativo) dentro de uma janela de 20 amostras, indicando instabilidade (chattering). |

<hr>

### Diagrama de Fluxo Principal (Algoritmo do Controlador)

```bash
graph TD
    A[INÍCIO: Configuração e Setup] --> B{Conectar MQTT & Iniciar Thread de Escuta};
    B --> C[Definir Universo e Conjuntos Fuzzy];
    C --> D[Gerar & Publicar Imagem das Regras];
    D --> E[Inicializar Variáveis Globais (T_n, Qest, Text)];
    E --> F{LOOP PRINCIPAL (a cada 0.1s)};

    F --> G[1. Calcular Erro (T_n - 22.0)];
    G --> H[2. Calcular Variação do Erro];

    H --> I[3. Injetar Entradas na Simulação Fuzzy];
    I --> J[4. Computar Inferência e Defuzzificação];
    J --> K[5. Obter Potência de Controle (PCRAC_val)];

    K --> L[6. TELEMETRIA: Publicar JSON e Gráfico B64 da Inferência];
    L --> M[7. SIMULAÇÃO DA PLANTA: Calcular T_next];

    M --> N[8. OUTPUT: Publicar T_next e PCRAC_val via MQTT];

    N --> O{9. VERIFICAÇÃO DE ALERTAS};
    O --> P1{T_next fora de [18, 26]?};
    P1 -- Sim --> Q1[Publicar Alerta CRÍTICO];
    P1 -- Não --> P2{PCRAC > 95% por 10s?};
    P2 -- Sim --> Q2[Publicar Alerta ALTA Eficiência];
    P2 -- Não/Cont. --> P3{Oscilação do Erro?};
    P3 -- Sim --> Q3[Publicar Alerta MÉDIA Estabilidade];
    P3 -- Não/Cont. --> R;

    R[10. ATUALIZAR ESTADO: T_n = T_next, erro_anterior = erro_atual];
    R --> S[11. Pausar (0.1s)];
    S --> F;
```

### Diagrama de Fluxo Principal (Algoritmo do Controlador)

```text
graph LR
    subgraph Controlador Python
        Python[fuzzy_controller.py]
    end

    subgraph Broker MQTT (test.mosquitto.org)
        Broker[Broker MQTT]
    end

    subgraph Dashboard Node-RED (Interface Web)
        A[Sliders: T. Externa, Carga Térmica]
        B[Gauges, Charts, Imagens, Alertas]
        C[Botão/Comando Reset]
    end

    %% Inputs (Perturbações)
    A -- entrada/temp/externa --> Broker
    A -- entrada/cargaTermica --> Broker
    Broker --> Python

    %% Saídas (Controle e Telemetria)
    Python -- datacenter/fuzzy/control --> Broker
    Python -- datacenter/fuzzy/temp --> Broker
    Python -- datacenter/fuzzy/alert (JSON) --> Broker
    Python -- datacenter/fuzzy/inference/img (B64) --> Broker

    %% Exibição no Node-RED
    Broker --> B

    %% Reset
    C -- datacenter/fuzzy/reset --> Broker
    Broker --> Python
```

## Dashboard Node-RED

O fluxo Node-RED provê uma interface de controle e monitoramento visual.

Para rodar, é necessário ter node e npm instalados

```text
node --version; npm --version
```

Install Node-RED

```bash
npm install -g --unsafe-perm node-red
```

Rodar

```bash
node-red
```

Acessar a porta e importar o flow utilizando o arquivos flow.json

#### Fluxo de Operação

O arquivo flow.json (código JSON do fluxo) define o seguinte:

1. Entradas de Perturbação: Sliders (ui_slider) publicam nos tópicos entrada/temp/externa e entrada/cargaTermica.
2. Visualização:
   - Temperatura e PCRAC: Exibidos em medidores (ui_gauge).
   - Histórico: A temperatura é traçada em um gráfico de linha (ui_chart).
   - Mapas Fuzzy: O gráfico das funções de pertinência (datacenter/fuzzy/img/rules) é exibido em um ui_template.
3. Processamento de Alertas: Um nó function parseia o payload JSON do tópico datacenter/fuzzy/alert e gera toasts coloridos no dashboard com base na severidade (crítica, alta, etc.).

<img src="/imagens/pertubacoes.png" alt="Perturbações" width="100%"/>
<img src="/imagens/monitoramento.png" alt="Monitoramento" width="100%"/>
<img src="/imagens/fuzzy_interface.png" alt="Interface fuzzy" width="100%"/>

### Alertas críticos e de comunicação

![Alerta Comunicação](/imagens/alerta_comunicacao.png)
![Alerta Temp Alta](/imagens/alerta_temp_alta.png)
![Alerta Temp Baixa](/imagens/alerta_temp_baixa.png)

### Testes Unitários

O projeto inclui um conjunto de testes unitários (test_controlador.py) utilizando a biblioteca unittest do Python.

Os testes garantem a integridade do sistema, cobrindo:

- Resiliência MQTT: Validação da função on_message contra payloads inválidos e a funcionalidade do comando TOPIC_RESET
- Lógica Fuzzy: Teste dos extremos do controlador (e.g., erro muito negativo deve resultar em $\text{PCRAC}$ mínima, erro muito positivo em $\text{PCRAC}$ máxima).
- Modelo de Planta: Validação da precisão matemática da equação de predição de temperatura.
- Alertas: Simulação e verificação do disparo correto dos alertas de Temperatura Crítica, Eficiência Máxima e Oscilação de Controle.

Rodar testes:

```bash
python test_controlador.py
```
