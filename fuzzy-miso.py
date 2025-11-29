import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import paho.mqtt.client as mqtt
import time
import json
import matplotlib.pyplot as plt
import io
import base64

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
T_SETPOINT = 22.0

TOPIC_CONTROL = "datacenter/fuzzy/control"
TOPIC_ALERT = "datacenter/fuzzy/alert"
TOPIC_TEMP = "datacenter/fuzzy/temp"
TOPIC_INPUT_TEXT = "entrada/temp/externa"
TOPIC_INPUT_QEST = "entrada/cargaTermica"
TOPIC_IMG_RULES = "datacenter/fuzzy/img/rules"

Text = 35.0
Qest = 40.0

errotemp = ctrl.Antecedent(np.arange(-16, 16.1, 1), 'errotemp')
varerrotemp = ctrl.Antecedent(np.arange(-2, 2.1, 0.1), 'varerrotemp')
pcrac = ctrl.Consequent(np.arange(0, 101, 1), 'pcrac')

errotemp['MN'] = fuzz.trapmf(errotemp.universe, [-16, -16,-12, -6])
errotemp['PN'] = fuzz.trimf(errotemp.universe, [-12, -6, 0])
errotemp['ZE'] = fuzz.trimf(errotemp.universe, [-6, 0, 6])
errotemp['PP'] = fuzz.trimf(errotemp.universe, [0, 6, 12])
errotemp['MP'] = fuzz.trapmf(errotemp.universe,[6, 12, 16,16])

varerrotemp['MN'] = fuzz.trapmf(varerrotemp.universe, [-2, -2, -0.2, -0.1])
varerrotemp['PN'] = fuzz.trimf(varerrotemp.universe, [-0.2, -0.1, 0])
varerrotemp['ZE'] = fuzz.trimf(varerrotemp.universe, [-0.1, 0, 0.1])
varerrotemp['PP'] = fuzz.trimf(varerrotemp.universe, [0, 0.1, 0.2])
varerrotemp['MP'] = fuzz.trapmf(varerrotemp.universe, [0.1, 0.2, 2, 2])

pcrac['MB'] = fuzz.trimf(pcrac.universe, [0, 0, 25])
pcrac['B']  = fuzz.trimf(pcrac.universe, [0, 25, 50])
pcrac['M']  = fuzz.trimf(pcrac.universe, [25, 50, 75])
pcrac['A']  = fuzz.trimf(pcrac.universe, [50, 75, 100])
pcrac['MA'] = fuzz.trimf(pcrac.universe, [75, 100, 100])

rules = []
erro_labels = ['MN', 'PN', 'ZE', 'PP', 'MP']
delta_labels = ['MN', 'PN', 'ZE', 'PP', 'MP']

matriz_saida = [
    ['B',  'M',  'A',  'A',  'MA' ],
    ['MB', 'B',  'M',  'A',  'MA' ],
    ['MB', 'B',  'B',  'M',  'MA' ],
    ['MB', 'MB', 'B',  'B',  'MA' ],
    ['MB', 'MB', 'MB', 'B',  'A'  ]
]

for i, d_label in enumerate(delta_labels):
    for j, e_label in enumerate(erro_labels):
        rules.append(ctrl.Rule(varerrotemp[d_label] & errotemp[e_label],
                               pcrac[matriz_saida[i][j]]))

sistema_controle = ctrl.ControlSystem(rules)
simulacao = ctrl.ControlSystemSimulation(sistema_controle)

def on_connect(client, userdata, flags, rc):
    client.subscribe(TOPIC_INPUT_TEXT)
    client.subscribe(TOPIC_INPUT_QEST)

def on_message(client, userdata, msg):
    global Text, Qest
    try:
        valor = float(msg.payload.decode())
        if msg.topic == TOPIC_INPUT_TEXT:
            Text = valor
        elif msg.topic == TOPIC_INPUT_QEST:
            Qest = valor
    except:
        pass

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

def gerar_graficos_base64():
    fig, (ax0, ax1, ax2) = plt.subplots(nrows=3, figsize=(6, 12))
    for label in errotemp.terms:
        ax0.plot(errotemp.universe, errotemp[label].mf, label=label)
    ax0.legend()
    for label in varerrotemp.terms:
        ax1.plot(varerrotemp.universe, varerrotemp[label].mf, label=label)
    ax1.legend()
    for label in pcrac.terms:
        ax2.plot(pcrac.universe, pcrac[label].mf, label=label)
    ax2.legend()
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return "data:image/png;base64," + img

img_data = gerar_graficos_base64()
client.publish(TOPIC_IMG_RULES, img_data, retain=True)

T_n = 22.0
PCRAC_val = 50.0
erro_anterior = 0.0

while True:
    erro_atual = T_n - T_SETPOINT
    var_erro = erro_atual - erro_anterior

    simulacao.input['errotemp'] = erro_atual
    simulacao.input['varerrotemp'] = var_erro

    try:
        simulacao.compute()
        PCRAC_val = simulacao.output['pcrac']
    except:
        pass

    T_next = (0.9 * T_n) - (0.08 * PCRAC_val) + (0.05 * Qest) + (0.02 * Text) + 3.5

    client.publish(TOPIC_CONTROL, round(PCRAC_val, 2))
    client.publish(TOPIC_TEMP, round(T_next, 2))

    if T_next < 18:
        client.publish(TOPIC_ALERT, json.dumps({"nivel":"CRITICO","msg":"Temp Baixa (<18)","val":round(T_next,2)}))
    elif T_next > 26:
        client.publish(TOPIC_ALERT, json.dumps({"nivel":"CRITICO","msg":"Temp Alta (>26)","val":round(T_next,2)}))
    else:
        client.publish(TOPIC_ALERT, json.dumps({"nivel":"OK","msg":"Normal"}))

    erro_anterior = erro_atual
    T_n = T_next
    time.sleep(0.1)
