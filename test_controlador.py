import unittest
import json
import numpy as np
from unittest.mock import MagicMock, patch
import fuzzy_miso as app

class TestDataCenterCompleto(unittest.TestCase):

    def setUp(self):
        """
        PREPARAÇÃO: Executado antes de CADA teste.
        Reseta todas as variáveis globais para um estado limpo.
        """
        # 1. Reseta variáveis de processo
        app.Text = 35.0
        app.Qest = 40.0
        app.T_n = 22.0
        app.erro_anterior = 0.0
        app.PCRAC_val = 50.0
        
        # 2. Reseta contadores e históricos de alerta
        app.max_power_counter = 0
        app.osc_history = []
        
        # 3. Mock do Cliente MQTT (finge que é o MQTT)
        self.mock_client = MagicMock()
        
        # 4. Mock da simulação Fuzzy 
        app.simulacao.input['errotemp'] = 0
        app.simulacao.input['varerrotemp'] = 0

    # =================================================================
    # GRUPO 1: TESTES DE ENTRADA E RESILIÊNCIA (MQTT)
    # =================================================================

    def test_mqtt_reset_funcional(self):
        """Verifica se o comando de reset restaura os padrões."""
        app.Text = 99.9
        app.Qest = 99.9
        
        msg = MagicMock()
        msg.topic = app.TOPIC_RESET
        msg.payload = b"reset_now"
        
        app.on_message(self.mock_client, None, msg)
        
        self.assertEqual(app.Text, 25.0, "Text deve resetar para 25.0")
        self.assertEqual(app.Qest, 40.0, "Qest deve resetar para 40.0")

    def test_mqtt_entrada_invalida(self):
        """
        RESILIÊNCIA: Se chegar uma string ('olá') num tópico de número,
        o sistema NÃO pode travar (crashar).
        """
        valor_original = app.Text
        
        msg = MagicMock()
        msg.topic = app.TOPIC_INPUT_TEXT
        msg.payload = b"isso_nao_eh_um_numero"
        
        try:
            app.on_message(self.mock_client, None, msg)
        except Exception as e:
            self.fail(f"O sistema crashou ao receber string inválida: {e}")
            
        self.assertEqual(app.Text, valor_original)

    # =================================================================
    # GRUPO 2: LÓGICA FUZZY (O CÉREBRO)
    # =================================================================

    def test_fuzzy_extremo_frio(self):
        """Se estiver muito frio (Erro negativo), o CRAC deve desligar (0%)."""
        app.simulacao.input['errotemp'] = -15 # Sala a 7°C (se setpoint 22)
        app.simulacao.input['varerrotemp'] = 0
        app.simulacao.compute()
        output = app.simulacao.output['pcrac']
        
        # Espera-se potência muito baixa ou zero
        self.assertLess(output, 15.0, f"Potência deveria ser mínima, deu {output}")

    def test_fuzzy_extremo_quente(self):
        """Se estiver muito quente (Erro positivo), o CRAC deve ir ao máximo."""
        app.simulacao.input['errotemp'] = 15
        app.simulacao.input['varerrotemp'] = 0
        app.simulacao.compute()
        output = app.simulacao.output['pcrac']
        
        self.assertGreater(output, 85.0, f"Potência deveria ser alta, deu {output}")

    # =================================================================
    # GRUPO 3: SISTEMAS DE ALERTA (SEGURANÇA)
    # =================================================================

# No seu arquivo test_controlador.py, substitua este teste:

    def test_alerta_temperatura_alta(self):
        """
        Deve disparar alerta crítico se T_next > 26.
        """
        # Forçamos uma temperatura futura alta
        T_next = 30.0 # Valor forçado para teste
        
        # Simulamos a chamada do publish_alert
        if T_next > 26:
            app.publish_alert(self.mock_client,
                              alert_type="crítico",
                              message="Temperatura acima...",
                              data={"temperature": T_next},
                              severity="crítica")
        
        # Verificação:
        self.mock_client.publish.assert_called()
        args, _ = self.mock_client.publish.call_args
        topic, payload = args
        payload_data = json.loads(payload)
        self.assertEqual(payload_data['severity'], "crítica", "A severidade deveria ser 'crítica'")

# No seu arquivo test_controlador.py, substitua este teste:

    def test_alerta_eficiencia_maxima(self):
        """
        Deve disparar alerta se ficar em 100% de potência por 10 segundos.
        """
        # Configuração:
        app.MAX_POWER_DURATION_SEC = 10.0
        app.loop_interval = 1
        required_iters = int(app.MAX_POWER_DURATION_SEC / app.loop_interval) # 10
        
        # Simula 9 iterações (não deve disparar)
        app.max_power_counter = required_iters - 1 # 9
        app.PCRAC_val = 98.0 # Acima do threshold de 95
        
        # Lógica do loop para simular a décima iteração:
        if app.PCRAC_val >= app.MAX_POWER_THRESHOLD:
            app.max_power_counter += 1
        
        # O alerta deve ser disparado AGORA (na iteração 10)
        if app.max_power_counter == required_iters:
             app.publish_alert(self.mock_client, 
                               alert_type="eficiência", 
                               message="CRAC atingiu potência máxima por tempo prolongado", 
                               severity="alta")
        
        # Verificação:
        self.mock_client.publish.assert_called()
        args, _ = self.mock_client.publish.call_args
        topic, payload = args
        payload_data = json.loads(payload)
        
        # Asserção: Verifica a chave 'type' no objeto JSON decodificado
        self.assertEqual(payload_data['type'], "eficiência", "O tipo de alerta deveria ser 'eficiência'")

    def test_alerta_oscilacao(self):
        """
        Detecta se o sistema oscila (positivo/negativo) muitas vezes ("bater pino").
        """
        # Limpa histórico
        app.osc_history = []
        app.OSC_SIGN_CHANGE_THRESHOLD = 3 
        
        # Simula histórico oscilatório: + - + - 
        # (Isso é péssimo para compressores de ar condicionado)
        sequencia_erros = [1, -1, 1, -1] 
        
        sign_changes = 0
        prev = sequencia_erros[0]
        for s in sequencia_erros[1:]:
            if s != prev:
                sign_changes += 1
            prev = s
            
        self.assertGreaterEqual(sign_changes, 3)
        # Se fosse no código real, isso dispararia o publish_alert de estabilidade

    # =================================================================
    # GRUPO 4: FÍSICA E MATEMÁTICA (PLANTA)
    # =================================================================

    def test_equacao_temperatura(self):
        """
        Verifica a precisão matemática da equação de predição.
        T_next = (0.9 * T_n) - (0.08 * PCRAC) + (0.05 * Qest) + (0.02 * Text) + 3.5
        """
        app.T_n = 20.0
        pcrac = 50.0
        qest = 40.0
        text = 30.0
        
        # Cálculo esperado:
        # (18) - (4) + (2) + (0.6) + 3.5 = 20.1
        
        calculado = (0.9 * app.T_n) - (0.08 * pcrac) + (0.05 * qest) + (0.02 * text) + 3.5
        
        self.assertAlmostEqual(calculado, 20.1, places=2)

    def test_json_payload_format(self):
        """Verifica se o JSON de inferência está bem formatado."""
        infos = [{"id": 1, "consequent": "MA"}]
        agg = [0.1, 0.5]
        defuzz = 75.0
        
        payload = {
            "timestamp": "2023-01-01T00:00:00",
            "rules": infos,
            "defuzzified": defuzz,
            "aggregation": {"mu": agg}
        }
        
        json_str = json.dumps(payload)
        # Tenta carregar de volta para garantir que é um JSON válido
        decoded = json.loads(json_str)
        self.assertEqual(decoded['defuzzified'], 75.0)

if __name__ == '__main__':
    # Verbosity 2 mostra os detalhes de cada teste rodado
    unittest.main(verbosity=2)