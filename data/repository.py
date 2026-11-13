"""Fachada de compatibilidade: a API continua em data.repository; a implementacao esta em data/repo_*.py."""
# noqa: F401,F403
from data.repo_base import *  # noqa: F401,F403
from data.repo_base import (
    _COLUNAS_CONTRIBUICAO, _PD_READ_SQL_QUERY, _autenticacao_bloqueada, _conn, _contar_membros_ativos_dashboard, _copia_consistente_sqlite, _dados_lancamento_validados, _data_dir, _db_subcategorias, _df_csv_seguro, _df_detalhes_dashboard, _digitos, _fazer_backup, _formatar_colunas_telefone, _funcao_recepcao_elegivel, _garantir_colunas_cadastros, _garantir_colunas_lancamentos, _garantir_ministerio_padrao, _garantir_tabela_biblia_audio_cache, _garantir_tabela_biblia_cache, _garantir_tabela_config, _garantir_tabela_config_igreja, _garantir_tabela_contribuicoes_online, _garantir_tabela_documentos_emitidos, _garantir_tabela_leitores_biblia, _garantir_tabela_leitura_confirmacoes, _garantir_tabela_pastores_auxiliares, _garantir_tabela_permissoes_usuarios, _garantir_tabela_plano_leitura, _garantir_tabela_pre_cadastros, _garantir_tabela_recepcao, _garantir_tabela_secretarios_gerais, _garantir_tabela_subcategorias_despesa, _garantir_tabela_tentativas_login, _garantir_tabela_tesoureiros, _garantir_tabelas_acesso_usuarios, _garantir_tabelas_ebd, _garantir_tabelas_eventos, _garantir_tabelas_geo_frequencia, _garantir_tabelas_gfc, _garantir_tabelas_obreiros, _garantir_tabelas_orhafe, _garantir_tabelas_pedidos_oracao, _garantir_tabelas_visitantes, _normalizar_lancamentos_dashboard, _normalizar_telefone_leitor, _normalizar_texto_sem_acento, _normalizar_tipo_culto_gfc, _normalizar_usuario_ebd, _normalizar_usuario_gfc, _normalizar_usuario_login_secretario_geral, _normalizar_usuario_orhafe, _normalizar_usuario_pastor_auxiliar, _normalizar_usuario_recepcao, _normalizar_usuario_secretario_geral, _normalizar_usuario_tesoureiro, _pin_recepcao_por_cpf, _read_sql_query_formatado, _registrar_resultado_login, _sincronizar_recepcao_automatica_conn, _sincronizar_recepcao_cadastro_conn, _substituir_banco_validado, _tenant_db, _usuario_login_por_nome, _usuario_recepcao_auto, _validar_comprovante, _validar_logo, _validar_pin_ebd, _validar_pin_gfc, _validar_pin_orhafe, _validar_pin_recepcao, _validar_senha_leitor_biblia, _validar_senha_pastor_auxiliar, _validar_senha_por_tipo_login, _validar_senha_secretario_geral, _validar_slug, _validar_tesoureiro, _verificar_senha,
)  # noqa: F401
from data.repo_logos import *  # noqa: F401,F403
from data.repo_gfc import *  # noqa: F401,F403
from data.repo_ebd import *  # noqa: F401,F403
from data.repo_lancamentos import *  # noqa: F401,F403
from data.repo_orhafe import *  # noqa: F401,F403
from data.repo_obreiros import *  # noqa: F401,F403
from data.repo_eventos import *  # noqa: F401,F403
from data.repo_cadastros import *  # noqa: F401,F403
from data.repo_cadastros import (
    _garantir_limite_membros, _limite_membros_da_igreja,
)  # noqa: F401
from data.repo_acesso import *  # noqa: F401,F403
from data.repo_visitantes import *  # noqa: F401,F403
from data.repo_equipe import *  # noqa: F401,F403
from data.repo_pedidos_oracao import *  # noqa: F401,F403
from data.repo_tesoureiros import *  # noqa: F401,F403
from data.repo_tesoureiros import (
    _dados_tesoureiro,
)  # noqa: F401
from data.repo_backup import *  # noqa: F401,F403
from data.repo_backup import (
    _extrair_banco_backup_igreja,
)  # noqa: F401
from data.repo_leitura_biblica import *  # noqa: F401,F403
from data.repo_contribuicoes import *  # noqa: F401,F403
from data.repo_documentos import *  # noqa: F401,F403
