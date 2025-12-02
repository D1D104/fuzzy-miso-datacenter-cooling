import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import paho.mqtt.client as mqtt
import time
import json
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timezone

MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
T_SETPOINT = 22.0

TOPIC_CONTROL = "datacenter/fuzzy/control"
TOPIC_ALERT = "datacenter/fuzzy/alert"
TOPIC_TEMP = "datacenter/fuzzy/temp"
TOPIC_INPUT_TEXT = "entrada/temp/externa"
TOPIC_INPUT_QEST = "entrada/cargaTermica"
TOPIC_IMG_RULES = "datacenter/fuzzy/img/rules"
TOPIC_INFERENCE = "datacenter/fuzzy/inference"
TOPIC_INFERENCE_IMG = "datacenter/fuzzy/inference/img"
TOPIC_RESET = "datacenter/fuzzy/reset"  

Text = 35.0
Qest = 40.0

errotemp = ctrl.Antecedent(np.arange(-16, 16.1, 1), 'errotemp')
varerrotemp = ctrl.Antecedent(np.arange(-2, 2.1, 0.1), 'varerrotemp')
pcrac = ctrl.Consequent(np.arange(0, 101, 1), 'pcrac')

errotemp['MN'] = fuzz.trapmf(errotemp.universe, [-16, -16, -12, -6])
errotemp['PN'] = fuzz.trimf(errotemp.universe, [-12, -6, 0])
errotemp['ZE'] = fuzz.trimf(errotemp.universe, [-6, 0, 6])
errotemp['PP'] = fuzz.trimf(errotemp.universe, [0, 6, 12])
errotemp['MP'] = fuzz.trapmf(errotemp.universe, [6, 12, 16, 16])

varerrotemp['MN'] = fuzz.trapmf(varerrotemp.universe, [-2, -2, -0.8, -0.4])
varerrotemp['PN'] = fuzz.trimf(varerrotemp.universe, [-0.8, -0.4, 0])
varerrotemp['ZE'] = fuzz.trimf(varerrotemp.universe, [-0.4, 0, 0.4])
varerrotemp['PP'] = fuzz.trimf(varerrotemp.universe, [0, 0.4, 0.8])
varerrotemp['MP'] = fuzz.trapmf(varerrotemp.universe, [0.4, 0.8, 2.1, 2.1])

pcrac['MB'] = fuzz.trimf(pcrac.universe, [0, 0, 25])
pcrac['B']  = fuzz.trimf(pcrac.universe, [0, 25, 50])
pcrac['M']  = fuzz.trimf(pcrac.universe, [25, 50, 75])
pcrac['A']  = fuzz.trimf(pcrac.universe, [50, 75, 100])
pcrac['MA'] = fuzz.trimf(pcrac.universe, [75, 100, 100])

rules = []
erro_labels = ['MN', 'PN', 'ZE', 'PP', 'MP']
delta_labels = ['MN', 'PN', 'ZE', 'PP', 'MP']

matriz_saida = [
    ['MB',  'MB',  'B',  'M',  'A' ],
    ['MB', 'B',  'M',  'A',  'MA' ],
    ['MB', 'B',  'M',  'A',  'MA' ],
    ['MB', 'B', 'M',  'A',  'MA' ],
    ['B', 'M', 'A', 'MA',  'MA'  ]
]

for i, d_label in enumerate(delta_labels):
    for j, e_label in enumerate(erro_labels):
        rules.append(ctrl.Rule(varerrotemp[d_label] & errotemp[e_label],
                               pcrac[matriz_saida[i][j]]))

sistema_controle = ctrl.ControlSystem(rules)
simulacao = ctrl.ControlSystemSimulation(sistema_controle)

def iso_ts():
    return datetime.now(timezone.utc).isoformat()

def publish_alert(client, alert_type, message, data=None, severity="média"):
    payload = {
        "timestamp": iso_ts(),
        "type": alert_type,
        "message": message,
        "data": data or {},
        "severity": severity
    }
    client.publish(TOPIC_ALERT, json.dumps(payload))

def on_connect(client, userdata, flags, rc):
    client.subscribe(TOPIC_INPUT_TEXT)
    client.subscribe(TOPIC_INPUT_QEST)
    client.subscribe(TOPIC_RESET)
    
    publish_alert(client,
                  alert_type="comunicação",
                  message="Conectado ao broker MQTT",
                  data={"broker": MQTT_BROKER, "port": MQTT_PORT},
                  severity="baixa")

def on_disconnect(client, userdata, rc):
    publish_alert(client,
                  alert_type="comunicação",
                  message="Desconexão do broker MQTT",
                  data={"reason_code": rc},
                  severity="crítica")

def on_message(client, userdata, msg):
    global Text, Qest
    
    if msg.topic == TOPIC_RESET:
        Text = 25.0
        Qest = 40.0
        print(f"RESET RECEBIDO: Text={Text}, Qest={Qest}")
        publish_alert(client, 
                      alert_type="operacional", 
                      message="Valores resetados manualmente", 
                      data={"Text": Text, "Qest": Qest}, 
                      severity="baixa")
        return 

    try:
        valor = float(msg.payload.decode())
        if msg.topic == TOPIC_INPUT_TEXT:
            Text = valor
        elif msg.topic == TOPIC_INPUT_QEST:
            Qest = valor
    except:
        pass


#########################################################################
# MQTT background loop explanation & graceful shutdown helper
#
# O que client.loop_start() faz?
# - Inicia uma thread separada que mantém a conexão com o broker MQTT (keep-alive).
# - Escuta continuamente o socket e processa mensagens recebidas.
# - Chama callbacks como on_message mesmo quando o loop principal (while True)
#   está parado ou aguardando.
#
# Por que ele continua rodando?
# - Quando você interrompe o loop principal (Ctrl+C), a thread de rede criada
#   por client.loop_start() continua ativa em segundo plano até que seja parada
#   explicitamente.
# - Para um encerramento limpo você precisa parar essa thread e desconectar o
#   cliente do broker.
#
# Como parar corretamente:
# - Use client.loop_stop() e client.disconnect() em um bloco try/finally para
#   garantir que sejam executados mesmo em interrupções (KeyboardInterrupt).
#
def graceful_shutdown(client):
    """Parar corretamente a thread MQTT e desconectar do broker.

    Executar client.loop_stop() seguido de client.disconnect() garante que a
    thread de rede seja parada e a conexão seja finalizada.
    """
    try:
        # Se cliente é None ou não implementa, falhará silenciosamente
        client.loop_stop()
    except Exception:
        pass
    try:
        client.disconnect()
    except Exception:
        pass


client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

def gerar_graficos_base64():
    fig, (ax0, ax1, ax2) = plt.subplots(nrows=3, figsize=(6, 12))
    for label in errotemp.terms:
        ax0.plot(errotemp.universe, errotemp[label].mf, label=label)
    ax0.axvline(0, color='k', linestyle='--', linewidth=0.8)
    ax0.legend()
    for label in varerrotemp.terms:
        ax1.plot(varerrotemp.universe, varerrotemp[label].mf, label=label)
    ax1.axvline(0, color='k', linestyle='--', linewidth=0.8)
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

MAX_POWER_THRESHOLD = 95.0
MAX_POWER_DURATION_SEC = 10.0
# default loop iterval (seconds) between samples — reduce to improve sampling rate
loop_interval = 0.1
max_power_counter = 0
max_power_required_iters = int(MAX_POWER_DURATION_SEC / loop_interval)
OSC_WINDOW = 20  # número de amostras na janela
osc_history = []  # armazena sinais de erro (positivo/negativo/zero)
OSC_SIGN_CHANGE_THRESHOLD = 6  # se houver mais que isso em janela, alerta
# Throttle: generation of the inference image is expensive (matplotlib). Only
# produce and publish the inference image every INFERENCE_IMG_PERIOD_SEC seconds
# (set to None to disable).
INFERENCE_IMG_PERIOD_SEC = 10.0
last_inference_img_at = 0.0

def inference_debug(erro_val, varerro_val, pcrac_universe, consequents_terms, antecedents):
    rule_infos = []
    ante_degrees = {}
    for a_name, (u, terms) in antecedents.items():
        ante_degrees[a_name] = {}
        val = erro_val if a_name == 'errotemp' else varerro_val
        for label, mf in terms.items():
            deg = fuzz.interp_membership(u, mf, val)
            ante_degrees[a_name][label] = float(deg)

    agg = np.zeros_like(pcrac_universe, dtype=float)

    rule_id = 0
    for i, d_label in enumerate(delta_labels):
        for j, e_label in enumerate(erro_labels):
            rule_id += 1
            deg_var = ante_degrees['varerrotemp'][d_label]
            deg_erro = ante_degrees['errotemp'][e_label]
            activation = float(min(deg_var, deg_erro))
            consequent_label = matriz_saida[i][j]
            cons_mf = consequents_terms[consequent_label]
            scaled = np.fmin(activation, cons_mf)
            agg = np.fmax(agg, scaled)
            rule_infos.append({
                "id": rule_id,
                "antecedents": {f"varerrotemp.{d_label}": round(deg_var, 6), f"errotemp.{e_label}": round(deg_erro, 6)},
                "activation": round(activation, 6),
                "consequent": consequent_label
            })

    try:
        defuzz_val = float(fuzz.defuzz(pcrac_universe, agg, 'centroid'))
    except Exception:
        defuzz_val = float('nan')

    return rule_infos, agg.tolist(), defuzz_val

def plot_inference(erro_val, varerro_val, pcrac_universe, antecedents, consequents_terms, rule_infos, agg_mu, defuzz_val):
    fig, axes = plt.subplots(3, 1, figsize=(9, 12))
    ax = axes[0]
    for label, mf in antecedents['errotemp'][1].items():
        ax.plot(antecedents['errotemp'][0], mf, label=f"erro:{label}")
    ax.axvline(erro_val, color='k', linestyle='--', label=f"erro={erro_val:.2f}")
    ax.set_title("Erro (errotemp)")
    ax.legend(loc='upper right', fontsize='small')

    ax = axes[1]
    for label, mf in antecedents['varerrotemp'][1].items():
        ax.plot(antecedents['varerrotemp'][0], mf, label=f"var:{label}")
    ax.axvline(varerro_val, color='k', linestyle='--', label=f"var={varerro_val:.3f}")
    ax.set_title("Variação do erro (varerrotemp)")
    ax.legend(loc='upper right', fontsize='small')

    ax = axes[2]
    for label, mf in consequents_terms.items():
        ax.plot(pcrac_universe, mf, color='gray', alpha=0.4)
    ax.fill_between(pcrac_universe, agg_mu, color='red', alpha=0.5, label='agregação')
    ax.axvline(defuzz_val, color='blue', linestyle='--', linewidth=1.5, label=f'defuzz={defuzz_val:.2f}')
    ax.set_title("Consequente (pcrac) - agregação e defuzzificação")
    ax.legend(loc='upper right', fontsize='small')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return "data:image/png;base64," + img_b64

if __name__ == "__main__":
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    img_data = gerar_graficos_base64()
    client.publish(TOPIC_IMG_RULES, img_data, retain=True)

    print("Sistema Fuzzy Iniciado. Aguardando comandos...")

    try:
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
            antecedents = {
                'errotemp': (errotemp.universe, {label: errotemp[label].mf for label in errotemp.terms}),
                'varerrotemp': (varerrotemp.universe, {label: varerrotemp[label].mf for label in varerrotemp.terms})
            }
            consequents_terms = {label: pcrac[label].mf for label in pcrac.terms}
            pcrac_universe = pcrac.universe

            rule_infos, agg_mu, defuzz_val = inference_debug(erro_atual, var_erro, pcrac_universe, consequents_terms, antecedents)

            inference_payload = {
                "timestamp": iso_ts(),
                "operating_point": {"T": round(T_n, 3), "pcrac": round(PCRAC_val, 3), "erro": round(erro_atual, 3), "var_erro": round(var_erro, 3)},
                "rules": rule_infos,
                "defuzzified": round(defuzz_val, 3),
                "aggregation": {"x": pcrac_universe.tolist(), "mu": [round(float(x), 6) for x in agg_mu]}
            }

            try:
                client.publish(TOPIC_INFERENCE, json.dumps(inference_payload))
            except Exception:
                pass

            try:
                img_data = plot_inference(erro_atual, var_erro, pcrac_universe, antecedents, consequents_terms, rule_infos, agg_mu, defuzz_val)
                client.publish(TOPIC_INFERENCE_IMG, img_data, retain=False)
            except Exception:
                pass

            T_next = (0.9 * T_n) - (0.072 * PCRAC_val) + (0.045 * Qest) + (0.02 * Text) + 3.5

            client.publish(TOPIC_CONTROL, round(PCRAC_val, 2))
            client.publish(TOPIC_TEMP, round(T_next, 2))

            if T_next < 18:
                publish_alert(client,
                            alert_type="crítico",
                            message="Temperatura abaixo do limite seguro",
                            data={"temperature": round(T_next, 2), "limit": 18.0},
                            severity="crítica")
            elif T_next > 26:
                publish_alert(client,
                            alert_type="crítico",
                            message="Temperatura acima do limite seguro",
                            data={"temperature": round(T_next, 2), "limit": 26.0},
                            severity="crítica")

            if PCRAC_val >= MAX_POWER_THRESHOLD:
                max_power_counter += 1
            else:
                if max_power_counter >= max_power_required_iters:
                    publish_alert(client,
                                alert_type="eficiência",
                                message="CRAC operou em potência máxima por período prolongado",
                                data={"pcrac": round(PCRAC_val, 2), "duration_sec": max_power_counter * loop_interval},
                                severity="alta")
                max_power_counter = 0

            if max_power_counter == max_power_required_iters:
                publish_alert(client,
                            alert_type="eficiência",
                            message="CRAC atingiu potência máxima por tempo prolongado",
                            data={"pcrac": round(PCRAC_val, 2), "duration_sec": max_power_counter * loop_interval},
                            severity="alta")

            sign = 0
            if erro_atual > 0.05:
                sign = 1
            elif erro_atual < -0.05:
                sign = -1

            if len(osc_history) >= OSC_WINDOW:
                osc_history.pop(0)
            osc_history.append(sign)

            sign_changes = 0
            prev = osc_history[0] if osc_history else 0
            for s in osc_history[1:]:
                if s != 0 and prev != 0 and s != prev:
                    sign_changes += 1
                if s != 0:
                    prev = s
                if sign_changes >= OSC_SIGN_CHANGE_THRESHOLD:
                    publish_alert(client,
                                alert_type="estabilidade",
                                message="Oscilações excessivas detectadas no erro de temperatura",
                                data={"sign_changes": sign_changes, "window_samples": len(osc_history), "erro_atual": round(erro_atual, 3)},
                                severity="média")
                    osc_history.clear()

                erro_anterior = erro_atual
                T_n = T_next
                time.sleep(loop_interval)

    except KeyboardInterrupt:
        print('\nInterrupção detectada. Encerrando graceful...')

    finally:
        graceful_shutdown(client)
        print('Cliente MQTT desconectado e loop parado.')
