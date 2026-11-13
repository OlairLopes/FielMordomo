import logging

import streamlit as st

from data.repository import (
    DIAS_DIZIMISTA_ATIVO_DEFAULT,
    adicionar_subcategoria_despesa,
    carregar_cadastros,
    definir_senha_pastoral,
    excluir_subcategoria_despesa,
    gerar_credencial_temporaria_acesso,
    igreja_alterar_senha,
    atualizar_situacao_acesso_usuario,
    inativar_pastor_auxiliar,
    inativar_recepcao_usuario,
    inativar_secretario_geral,
    listar_acessos_usuarios,
    listar_pastores_auxiliares,
    listar_recepcao_usuarios,
    listar_secretarios_gerais,
    listar_subcategorias_despesa,
    obter_config_igreja,
    obter_permissoes_usuario,
    redefinir_senha_acesso_usuario,
    salvar_pastor_auxiliar,
    salvar_permissoes_usuario,
    salvar_recepcao_usuario,
    salvar_secretario_geral,
    salvar_config_igreja,
    senha_pastoral_configurada,
    validar_nova_senha,
)
from utils.helpers import slug_da_sessao
from utils.planos import obter_plano
from utils.helpers import cabecalho_modulo


LOGGER = logging.getLogger(__name__)
OPCOES_DIAS = [30, 60, 90, 120]
MODULOS_LIBERAVEIS = {
    "cadastros": "Membros",
    "lancamentos": "Lancamentos",
    "relatorios": "Relatorios",
    "dashboard": "Dashboard",
    "ebd": "Escola Biblica",
    "orhafe": "Circulo de Oracao",
    "obreiros": "Reuniao de Obreiros",
    "eventos": "Agenda",
    "visitantes": "Visitantes",
    "pedidos_oracao": "Pedidos de Oracao",
    "aniversariantes": "Aniversarios",
}
SITUACOES_ACESSO = ["Ativo", "Inativo", "Bloqueado"]
MENSAGEM_ESCALA_EBD_PADRAO = """Paz do Senhor, {nome}!

Voce esta escalado(a) para servir na Escola Bíblica.
Data: {data}
Classe: {classe}
Funcao: {funcao}
Tema: {tema}

Contamos com sua presenca e dedicacao. Deus abencoe!"""


def _encerrar_sessao():
    for key in (
        "autenticado", "modo", "igreja", "tesoureiro", "secretario_ebd",
        "secretaria_orhafe", "pastor_auxiliar", "recepcao", "pagina", "mostrar_recuperacao",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state.keys()):
        if key.startswith(("df_", "lote_", "nl_counter_", "dashboard_", "_auth_", "_edit_", "_del_")):
            st.session_state.pop(key, None)


def _config_dias(slug):
    valor = obter_config_igreja(
        slug, "dias_dizimista_ativo", str(DIAS_DIZIMISTA_ATIVO_DEFAULT)
    )
    try:
        dias = int(valor)
    except (ValueError, TypeError):
        dias = DIAS_DIZIMISTA_ATIVO_DEFAULT
    return dias if dias in OPCOES_DIAS else DIAS_DIZIMISTA_ATIVO_DEFAULT


def _numero_config(valor, padrao=0.0):
    texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return float(padrao)
    return numero if numero >= 0 else float(padrao)


def _membros_opcoes(slug):
    df = carregar_cadastros(slug)
    if df.empty:
        return {}, df
    membros = df[
        (df["tipo_cadastro"].astype(str).str.upper() == "MEMBRO")
        & (df["situacao"].astype(str).str.upper() == "ATIVO")
    ].copy()
    membros = membros.sort_values("nome")
    opcoes = {
        f'{int(row["id_cadastro"])} - {row["nome"]}': int(row["id_cadastro"])
        for _, row in membros.iterrows()
    }
    return opcoes, membros


CONFIG_PASTOR_AUXILIAR = {
    "campo_id": "id_pastor_auxiliar",
    "titulo": "Pastores auxiliares",
    "descricao": (
        "Cadastre acessos restritos para pastor auxiliar. A senha deve possuir "
        "ao menos 8 caracteres."
    ),
    "rotulo_membro_selectbox": "Pastor auxiliar",
    "rotulo_credencial": "Senha forte",
    "credencial_help_novo": "Minimo de 8 caracteres.",
    "credencial_max_chars": None,
    "colunas_tabela": ["id_cadastro", "nome", "usuario", "telefone", "email", "situacao"],
    "expander_cadastrar": "Cadastrar pastor auxiliar",
    "submit_cadastrar": "Salvar pastor auxiliar",
    "sucesso_cadastrar": "Pastor Auxiliar cadastrado.",
    "rotulo_editar_select": "Editar pastor auxiliar",
    "rotulo_nova_credencial": "Nova senha",
    "submit_editar": "Atualizar pastor auxiliar",
    "sucesso_editar": "Pastor Auxiliar atualizado.",
    "botao_inativar": "Inativar pastor auxiliar selecionado",
    "sucesso_inativar": "Pastor Auxiliar inativado.",
    "vazio": "Nenhum Pastor Auxiliar cadastrado.",
    "listar": listar_pastores_auxiliares,
    "salvar": salvar_pastor_auxiliar,
    "inativar": inativar_pastor_auxiliar,
}

CONFIG_SECRETARIO_GERAL = {
    "campo_id": "id_secretario_geral",
    "titulo": "Secretarios gerais",
    "descricao": (
        "Cadastre acessos restritos para Secretaria Geral. Este perfil acessa "
        "membros, aniversarios e somente a chamada das reunioes de obreiros."
    ),
    "rotulo_membro_selectbox": "Secretario Geral",
    "rotulo_credencial": "Senha forte",
    "credencial_help_novo": "Minimo de 8 caracteres.",
    "credencial_max_chars": None,
    "colunas_tabela": ["id_cadastro", "nome", "usuario", "telefone", "email", "situacao"],
    "expander_cadastrar": "Cadastrar Secretario Geral",
    "submit_cadastrar": "Salvar Secretario Geral",
    "sucesso_cadastrar": "Secretario Geral cadastrado.",
    "rotulo_editar_select": "Editar Secretario Geral",
    "rotulo_nova_credencial": "Nova senha",
    "submit_editar": "Atualizar Secretario Geral",
    "sucesso_editar": "Secretario Geral atualizado.",
    "botao_inativar": "Inativar Secretario Geral selecionado",
    "sucesso_inativar": "Secretario Geral inativado.",
    "vazio": "Nenhum Secretario Geral cadastrado.",
    "listar": listar_secretarios_gerais,
    "salvar": salvar_secretario_geral,
    "inativar": inativar_secretario_geral,
}

CONFIG_RECEPCAO = {
    "campo_id": "id_recepcao",
    "titulo": "Recepção",
    "descricao": (
        "Diáconos, diaconisas, auxiliares e cooperadoras ativos são incluídos "
        "automaticamente. Usuário automático: nome completo sem acentos, em "
        "minúsculas e com espaços convertidos em ponto. Exemplo: joao.da.silva. "
        "PIN inicial: últimos 4 dígitos do CPF. Esse perfil acessa somente "
        "visitantes."
    ),
    "rotulo_membro_selectbox": "Recepcionista",
    "rotulo_credencial": "PIN de 4 digitos",
    "credencial_help_novo": None,
    "credencial_max_chars": 4,
    "colunas_tabela": [
        "id_cadastro", "nome", "usuario", "telefone", "email", "situacao", "automatico",
    ],
    "expander_cadastrar": "Cadastrar usuario da recepção",
    "submit_cadastrar": "Salvar recepção",
    "sucesso_cadastrar": "Usuário da Recepção cadastrado.",
    "rotulo_editar_select": "Editar usuario da recepção",
    "rotulo_nova_credencial": "Novo PIN de 4 digitos",
    "submit_editar": "Atualizar recepção",
    "sucesso_editar": "Usuário da Recepção atualizado.",
    "botao_inativar": "Inativar usuario da recepção",
    "sucesso_inativar": "Usuário da Recepção inativado.",
    "vazio": "Nenhum usuário da Recepção cadastrado.",
    "listar": listar_recepcao_usuarios,
    "salvar": salvar_recepcao_usuario,
    "inativar": inativar_recepcao_usuario,
}


def _render_secao_acesso_restrito(slug, op_membros, df_membros, config):
    """Renderiza uma secao de acesso restrito (cadastrar/editar/inativar),
    parametrizada por perfil (pastor auxiliar, secretario geral, recepcao).
    As tres secoes eram praticamente identicas; aqui o texto e o
    comportamento visivel de cada uma sao preservados via `config`."""
    campo_id = config["campo_id"]

    st.divider()
    st.markdown(f"### {config['titulo']}")
    st.caption(config["descrição"])

    try:
        registros = config["listar"](slug)
    except Exception:
        LOGGER.exception("Nao foi possivel carregar %s.", config["titulo"].lower())
        registros = None
        st.error(f"Não foi possível carregar {config['titulo'].lower()}.")

    with st.expander(config["expander_cadastrar"], expanded=False):
        with st.form(f"form_{campo_id}_novo"):
            id_cadastro = None
            nome = ""
            telefone = ""
            if not op_membros:
                st.warning("Não há membros ativos disponíveis no cadastro.")
            else:
                membro_label = st.selectbox(
                    config["rotulo_membro_selectbox"],
                    list(op_membros.keys()),
                    help="A lista traz somente membros ativos cadastrados.",
                    key=f"{campo_id}_membro",
                )
                id_cadastro = op_membros[membro_label]
                row_membro = df_membros[
                    df_membros["id_cadastro"].astype(int) == int(id_cadastro)
                ].iloc[0]
                c1, c2 = st.columns(2)
                c1.text_input(
                    "Nome", value=row_membro.get("nome", ""), disabled=True,
                    key=f"{campo_id}_nome_ro",
                )
                c2.text_input(
                    "Telefone", value=row_membro.get("telefone", ""), disabled=True,
                    key=f"{campo_id}_tel_ro",
                )
                nome = row_membro.get("nome", "")
                telefone = row_membro.get("telefone", "")
            c3, c4 = st.columns(2)
            usuario = c3.text_input("Usuario", key=f"{campo_id}_usuario_novo")
            senha = c4.text_input(
                config["rotulo_credencial"],
                type="password",
                help=config["credencial_help_novo"],
                max_chars=config["credencial_max_chars"],
                key=f"{campo_id}_senha_novo",
            )
            email = st.text_input(
                "E-mail", help="Opcional.", key=f"{campo_id}_email_novo"
            )
            observacoes = st.text_area("Observações", key=f"{campo_id}_obs_novo")
            if st.form_submit_button(config["submit_cadastrar"], type="primary"):
                try:
                    if not id_cadastro:
                        st.error("Selecione um membro para criar o acesso.")
                    else:
                        config["salvar"](
                            slug,
                            nome,
                            usuario,
                            senha,
                            id_cadastro=id_cadastro,
                            telefone=telefone,
                            email=email,
                            situacao="Ativo",
                            observacoes=observacoes,
                        )
                        st.success(config["sucesso_cadastrar"])
                        st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if registros is not None and not registros.empty:
        st.dataframe(
            registros[config["colunas_tabela"]],
            use_container_width=True,
            hide_index=True,
        )
        opcoes = {
            f'{int(row[campo_id])} - {row["nome"]} - {row["usuario"]}': row
            for _, row in registros.iterrows()
        }
        selecionado = st.selectbox(
            config["rotulo_editar_select"],
            ["Selecione"] + list(opcoes.keys()),
            key=f"{campo_id}_sel_editar",
        )
        if selecionado != "Selecione":
            row = opcoes[selecionado]
            id_registro = int(row[campo_id])
            with st.form(f"form_editar_{campo_id}_{id_registro}"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome", value=row["nome"])
                usuario = c2.text_input("Usuario", value=row["usuario"])
                c3, c4 = st.columns(2)
                nova_senha = c3.text_input(
                    config["rotulo_nova_credencial"],
                    type="password",
                    max_chars=config["credencial_max_chars"],
                    help="Deixe em branco para manter a senha atual.",
                )
                situacao = c4.selectbox(
                    "Situacao",
                    ["Ativo", "Inativo"],
                    index=0 if row.get("situacao") == "Ativo" else 1,
                    key=f"{campo_id}_situacao_{id_registro}",
                )
                telefone = st.text_input("Telefone", value=row.get("telefone", ""))
                email = st.text_input("E-mail", value=row.get("email", ""))
                observacoes = st.text_area(
                    "Observações", value=row.get("observacoes", "")
                )
                if st.form_submit_button(config["submit_editar"], type="primary"):
                    try:
                        config["salvar"](
                            slug,
                            nome,
                            usuario,
                            nova_senha,
                            id_cadastro=row.get("id_cadastro"),
                            telefone=telefone,
                            email=email,
                            situacao=situacao,
                            observacoes=observacoes,
                            **{campo_id: id_registro},
                        )
                        st.success(config["sucesso_editar"])
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            if st.button(config["botao_inativar"], key=f"{campo_id}_inativar_{id_registro}"):
                config["inativar"](slug, id_registro)
                st.success(config["sucesso_inativar"])
                st.rerun()
    elif registros is not None:
        st.info(config["vazio"])


def _render_controle_acessos(slug):
    st.divider()
    st.markdown("### Controle de acessos")
    st.caption(
        "Ative, inative ou bloqueie usuarios operacionais e libere módulos extras "
        "sem conceder acesso a areas sensiveis como Backup, Tesoureiros e Minha Conta."
    )
    try:
        acessos = listar_acessos_usuarios(slug)
    except Exception:
        LOGGER.exception("Nao foi possivel carregar controle de acessos.")
        st.error("Não foi possível carregar o controle de acessos.")
        return

    if acessos.empty:
        st.info("Nenhum usuario operacional cadastrado.")
        return

    st.dataframe(
        acessos[["tipo", "nome", "usuario", "situacao"]],
        use_container_width=True,
        hide_index=True,
    )
    opcoes = {
        f'{row["tipo"]} - {row["nome"]} ({row["usuario"]})': row
        for _, row in acessos.iterrows()
    }
    selecionado = st.selectbox("Usuario para configurar", list(opcoes.keys()))
    row = opcoes[selecionado]
    tipo_login = row["tipo_login"]
    id_usuario = int(row["id_usuario"])
    permissoes_atuais = obter_permissoes_usuario(slug, tipo_login, id_usuario)

    with st.form(f"form_controle_acesso_{tipo_login}_{id_usuario}"):
        situacao_atual = row.get("situacao") if row.get("situacao") in SITUACOES_ACESSO else "Ativo"
        situacao = st.selectbox(
            "Situacao do acesso",
            SITUACOES_ACESSO,
            index=SITUACOES_ACESSO.index(situacao_atual),
        )
        modulos = st.multiselect(
            "Modulos extras liberados",
            list(MODULOS_LIBERAVEIS.keys()),
            default=[m for m in permissoes_atuais if m in MODULOS_LIBERAVEIS],
            format_func=lambda chave: MODULOS_LIBERAVEIS.get(chave, chave),
            help="Permissoes padrao do perfil continuam ativas. Aqui voce adiciona apenas liberacoes extras.",
        )
        if st.form_submit_button("Salvar controle de acesso", type="primary"):
            try:
                atualizar_situacao_acesso_usuario(slug, tipo_login, id_usuario, situacao)
                salvar_permissoes_usuario(slug, tipo_login, id_usuario, modulos)
                st.success("Controle de acesso atualizado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.expander("Redefinir senha ou PIN deste usuario", expanded=False):
        st.warning(
            "Esta ação não mostra a senha antiga. Ela substitui a credencial atual "
            "por uma temporaria. Entregue a nova credencial somente ao proprio usuario."
        )
        confirmar_reset = st.checkbox(
            "Confirmo que validei a identidade do usuario antes de redefinir o acesso",
            key=f"confirmar_reset_{tipo_login}_{id_usuario}",
        )
        if st.button(
            "Gerar credencial temporaria",
            type="primary",
            disabled=not confirmar_reset,
            key=f"btn_reset_senha_{tipo_login}_{id_usuario}",
        ):
            try:
                credencial_temporaria = gerar_credencial_temporaria_acesso(tipo_login)
                redefinir_senha_acesso_usuario(
                    slug, tipo_login, id_usuario, credencial_temporaria
                )
            except Exception as exc:
                LOGGER.exception("Nao foi possivel redefinir a credencial do usuario.")
                st.error(str(exc))
            else:
                st.success("Credencial temporaria gerada. Copie agora; ela nao sera exibida novamente.")
                st.code(credencial_temporaria)
                st.caption(
                    "Oriente o usuario a entrar com esta credencial e alterar a senha "
                    "assim que acessar o sistema."
                )


def render():
    cabecalho_modulo("Minha Conta")

    slug = slug_da_sessao()
    igreja = st.session_state.get("igreja", {})

    if not isinstance(igreja, dict) or not igreja or not slug:
        st.error("Sessão invalida. Faça login novamente.")
        return

    st.markdown("### Dados da igreja")

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nome da igreja", value=igreja.get("nome", ""), disabled=True)
        st.text_input("Identificador (slug)", value=igreja.get("slug", ""), disabled=True)
    with col2:
        st.text_input("E-mail do admin", value=igreja.get("email_admin", ""), disabled=True)

        plano = igreja.get("plano", "basico")
        p_info = obter_plano(plano)
        st.text_input(
            "Plano atual",
            value=f"{p_info['nome']} - {p_info.get('preco', '')}",
            disabled=True,
        )

    st.caption(
        "Para alterar nome, e-mail ou plano, entre em contato com o administrador do sistema."
    )

    st.divider()
    st.markdown("### Configuracoes da igreja")
    st.caption("Personalize critérios usados nos relatórios, dashboard e comprovantes.")

    try:
        dias_atual = _config_dias(slug)
        assinatura_atual = obter_config_igreja(
            slug, "nome_assinatura_comprovante", "Responsavel"
        )
        reserva_atual = _numero_config(
            obter_config_igreja(slug, "reserva_financeira_disponivel", "0")
        )
        meta_reserva_atual = int(_numero_config(
            obter_config_igreja(slug, "meta_reserva_meses", "3"), 3
        ))
        mensagem_ebd_atual = obter_config_igreja(
            slug, "mensagem_whatsapp_escala_ebd", MENSAGEM_ESCALA_EBD_PADRAO
        )
        codigo_cadastro_atual = obter_config_igreja(
            slug, "codigo_atualizacao_cadastral", ""
        )
        nome_pastor_oracao_atual = obter_config_igreja(
            slug, "nome_pastor_oracao", "Pastor"
        )
        whatsapp_pastor_oracao_atual = obter_config_igreja(
            slug, "whatsapp_pastor_oracao", ""
        )
        mensagem_oracao_atual = obter_config_igreja(
            slug,
            "mensagem_whatsapp_pedido_oracao",
            """Paz do Senhor!

Novo pedido recebido pelo FielMordomo.

Congregacao: {congregacao}
Membro: {nome}
Tipo: {tipo}
Motivo: {motivo}
Privacidade: {privacidade}
Solicitou visita: {visita}
Horario da visita: {horario}

Pedido:
{pedido}
""",
        )
    except Exception:
        LOGGER.exception("Nao foi possivel carregar as configuracoes da igreja.")
        st.error("Não foi possível carregar as configurações. Tente novamente.")
        return

    idx_atual = OPCOES_DIAS.index(dias_atual)

    with st.form("form_config_igreja"):
        st.markdown("**Dizimista ativo**")
        st.caption(
            "Um membro e considerado dizimista ativo se contribuiu com dízimo "
            "nos últimos N dias."
        )

        dias_novo = st.selectbox(
            "Dias para considerar dizimista ativo",
            OPCOES_DIAS,
            index=idx_atual,
            format_func=lambda x: f"{x} dias" + (
                "  (mensal)" if x == 30 else
                "  (bimestral)" if x == 60 else
                "  (trimestral)" if x == 90 else
                "  (quadrimestral)"
            ),
            help="Padrao do sistema: 30 dias.",
        )

        assinatura_nova = st.text_input(
            "Nome da assinatura nos comprovantes",
            value=str(assinatura_atual or "Responsavel"),
            max_chars=100,
            help="Exemplo: Pr. Joao Silva ou Tesoureiro Responsavel.",
        )

        st.markdown("**Saude financeira**")
        st.caption(
            "Informe a reserva financeira separada para emergencias e a meta de cobertura. "
            "Esses valores alimentam o painel de saude financeira."
        )
        reserva_nova = st.text_input(
            "Reserva financeira disponível",
            value=f"{reserva_atual:.2f}".replace(".", ","),
            help="Informe apenas recursos realmente disponíveis como reserva.",
        )
        opcoes_meta = list(range(1, 13))
        meta_reserva_nova = st.selectbox(
            "Meta de cobertura da reserva",
            opcoes_meta,
            index=opcoes_meta.index(meta_reserva_atual) if meta_reserva_atual in opcoes_meta else 2,
            format_func=lambda meses: f"{meses} mes(es)",
        )

        st.markdown("**Mensagem da escala da Escola Bíblica**")
        st.caption(
            "Use as variaveis {nome}, {data}, {classe}, {funcao} e {tema}. "
            "Elas serao preenchidas automaticamente ao gerar o aviso pelo WhatsApp."
        )
        mensagem_ebd_nova = st.text_area(
            "Modelo da mensagem WhatsApp para professores da Escola Bíblica",
            value=str(mensagem_ebd_atual or MENSAGEM_ESCALA_EBD_PADRAO),
            height=180,
        )

        st.markdown("**Atualização cadastral pública**")
        st.caption(
            "Código divulgado internamente para membros atualizarem ou enviarem "
            "pre-cadastro pela página institucional."
        )
        codigo_cadastro_novo = st.text_input(
            "Código de atualização cadastral",
            value=str(codigo_cadastro_atual or ""),
            max_chars=30,
            help="Exemplo: AD2026 ou MEMBROS2026.",
        )

        st.markdown("**Pedidos de oracao e visita pastoral**")
        st.caption(
            "Configure o contato pastoral que recebera notificacoes. "
            "Pastores auxiliares ativos com telefone cadastrado também serao notificados."
        )
        p1, p2 = st.columns(2)
        nome_pastor_oracao_novo = p1.text_input(
            "Nome do pastor responsavel",
            value=str(nome_pastor_oracao_atual or "Pastor"),
            max_chars=100,
        )
        whatsapp_pastor_oracao_novo = p2.text_input(
            "WhatsApp do pastor para pedidos de oracao",
            value=str(whatsapp_pastor_oracao_atual or ""),
            placeholder="Ex.: 62999999999",
            max_chars=20,
        )
        st.caption(
            "Use as variaveis {congregacao}, {nome}, {tipo}, {motivo}, "
            "{privacidade}, {confidencial}, {visita}, {horario} e {pedido}."
        )
        mensagem_oracao_nova = st.text_area(
            "Modelo da mensagem WhatsApp para pedidos de oracao",
            value=str(mensagem_oracao_atual or ""),
            height=180,
        )

        if st.form_submit_button("Salvar configurações", type="primary"):
            assinatura_nova = assinatura_nova.strip()
            reserva_numero = _numero_config(reserva_nova, -1)
            if not assinatura_nova:
                st.error("Informe o nome da assinatura dos comprovantes.")
            elif reserva_numero < 0:
                st.error("Informe uma reserva financeira válida.")
            else:
                try:
                    salvar_config_igreja(slug, "dias_dizimista_ativo", str(dias_novo))
                    salvar_config_igreja(
                        slug, "nome_assinatura_comprovante", assinatura_nova
                    )
                    salvar_config_igreja(
                        slug, "reserva_financeira_disponivel", f"{reserva_numero:.2f}"
                    )
                    salvar_config_igreja(
                        slug, "meta_reserva_meses", str(meta_reserva_nova)
                    )
                    salvar_config_igreja(
                        slug, "mensagem_whatsapp_escala_ebd", mensagem_ebd_nova.strip()
                    )
                    salvar_config_igreja(
                        slug, "codigo_atualizacao_cadastral", codigo_cadastro_novo.strip()
                    )
                    salvar_config_igreja(
                        slug, "nome_pastor_oracao", nome_pastor_oracao_novo.strip()
                    )
                    salvar_config_igreja(
                        slug, "whatsapp_pastor_oracao", whatsapp_pastor_oracao_novo.strip()
                    )
                    salvar_config_igreja(
                        slug, "mensagem_whatsapp_pedido_oracao", mensagem_oracao_nova.strip()
                    )
                except Exception:
                    LOGGER.exception("Nao foi possivel salvar as configuracoes da igreja.")
                    st.error("Não foi possível salvar as configurações. Tente novamente.")
                else:
                    st.toast("Configurações salvas!")
                    st.rerun()

    st.divider()
    st.markdown("### Subcategorias de despesas")
    st.caption(
        "Cadastre as classificacoes usadas nos lançamentos de saída. "
        "Essa lista pertence a esta igreja e aparece no módulo Lançamentos."
    )

    try:
        subcategorias = listar_subcategorias_despesa(slug)
    except Exception:
        LOGGER.exception("Nao foi possivel carregar as subcategorias de despesa.")
        subcategorias = []
        st.error("Não foi possível carregar as subcategorias.")

    if subcategorias:
        st.dataframe(
            [{"Subcategoria": nome} for nome in subcategorias],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhuma subcategoria cadastrada.")

    with st.form("form_adicionar_subcategoria", clear_on_submit=True):
        nova_subcategoria = st.text_input(
            "Nova subcategoria",
            max_chars=80,
            placeholder="Exemplo: Agua, Energia, Missoes, Manutencao...",
        )
        if st.form_submit_button("Adicionar subcategoria", type="primary"):
            nome = nova_subcategoria.strip()
            if not nome:
                st.error("Informe o nome da subcategoria.")
            else:
                try:
                    adicionada = adicionar_subcategoria_despesa(nome, slug)
                except Exception:
                    LOGGER.exception("Nao foi possivel adicionar a subcategoria.")
                    st.error("Não foi possível adicionar a subcategoria.")
                else:
                    if adicionada:
                        st.toast("Subcategoria adicionada!")
                        st.rerun()
                    else:
                        st.warning("Essa subcategoria já existe ou e invalida.")

    if subcategorias:
        with st.form("form_excluir_subcategoria"):
            remover_subcategoria = st.selectbox(
                "Subcategoria para excluir",
                subcategorias,
                help=(
                    "A exclusao remove a opcao da lista. Lancamentos antigos "
                    "continuam preservando o texto ja salvo."
                ),
            )
            confirmar_remocao = st.checkbox(
                "Confirmo que desejo remover esta subcategoria da lista"
            )
            if st.form_submit_button("Excluir subcategoria"):
                if not confirmar_remocao:
                    st.error("Confirme a exclusão antes de continuar.")
                else:
                    try:
                        excluir_subcategoria_despesa(remover_subcategoria, slug)
                    except Exception:
                        LOGGER.exception("Nao foi possivel excluir a subcategoria.")
                        st.error("Não foi possível excluir a subcategoria.")
                    else:
                        st.toast("Subcategoria excluída.")
                        st.rerun()

    st.divider()
    st.markdown("### Senha do acompanhamento pastoral")
    st.caption(
        "Cadastre uma senha exclusiva para proteger os dados individuais de contribuição. "
        "Ela deve ser diferente da senha principal da igreja."
    )
    try:
        pastoral_configurada = senha_pastoral_configurada(slug)
    except Exception:
        LOGGER.exception("Nao foi possivel consultar a senha pastoral.")
        pastoral_configurada = False
        st.error("Não foi possível verificar a configuração da senha pastoral.")
    else:
        if pastoral_configurada:
            st.success("Senha pastoral cadastrada. Use o formulario para substitui-la.")
        else:
            st.warning("Cadastre uma senha pastoral para liberar o acompanhamento pastoral.")

    with st.form("form_senha_pastoral", clear_on_submit=True):
        senha_principal = st.text_input(
            "Senha principal da igreja",
            type="password",
            key="senha_principal_para_pastoral",
        )
        nova_senha_pastoral = st.text_input(
            "Nova senha pastoral",
            type="password",
            key="nova_senha_pastoral",
        )
        confirma_senha_pastoral = st.text_input(
            "Confirmar senha pastoral",
            type="password",
            key="confirma_senha_pastoral",
        )
        if st.form_submit_button(
            "Salvar senha pastoral" if not pastoral_configurada else "Alterar senha pastoral",
            type="primary",
        ):
            erros = []
            if not senha_principal:
                erros.append("Informe a senha principal da igreja.")
            erros.extend(validar_nova_senha(nova_senha_pastoral))
            if nova_senha_pastoral != confirma_senha_pastoral:
                erros.append("Senha pastoral e confirmacao nao coincidem.")

            if erros:
                for erro in dict.fromkeys(erros):
                    st.error(erro)
            else:
                try:
                    alterada = definir_senha_pastoral(
                        slug, senha_principal, nova_senha_pastoral
                    )
                except ValueError as ex:
                    st.error(str(ex))
                except Exception:
                    LOGGER.exception("Nao foi possivel salvar a senha pastoral.")
                    st.error("Não foi possível salvar a senha pastoral. Tente novamente.")
                else:
                    if alterada:
                        st.success("Senha pastoral salva com sucesso.")
                        st.rerun()
                    else:
                        st.error("Senha principal incorreta.")

    try:
        op_membros, df_membros = _membros_opcoes(slug)
    except Exception:
        LOGGER.exception("Nao foi possivel carregar os membros ativos.")
        op_membros, df_membros = {}, None
        st.error("Não foi possível carregar os membros ativos.")

    _render_secao_acesso_restrito(slug, op_membros, df_membros, CONFIG_PASTOR_AUXILIAR)
    _render_secao_acesso_restrito(slug, op_membros, df_membros, CONFIG_SECRETARIO_GERAL)
    _render_secao_acesso_restrito(slug, op_membros, df_membros, CONFIG_RECEPCAO)

    _render_controle_acessos(slug)

    st.divider()
    st.markdown("### Alterar senha principal")
    st.caption(
        "Use uma senha longa e exclusiva. A nova senha deve possuir entre "
        "15 e 128 caracteres."
    )

    with st.form("form_trocar_senha", clear_on_submit=True):
        senha_atual = st.text_input("Senha atual", type="password")
        nova_senha = st.text_input("Nova senha", type="password")
        confirma = st.text_input("Confirmar nova senha", type="password")

        if st.form_submit_button("Alterar senha", type="primary"):
            erros = []
            if not senha_atual:
                erros.append("Informe a senha atual.")
            erros.extend(validar_nova_senha(nova_senha))
            if nova_senha != confirma:
                erros.append("Nova senha e confirmacao nao coincidem.")

            if erros:
                for erro in dict.fromkeys(erros):
                    st.error(erro)
            else:
                try:
                    alterada = igreja_alterar_senha(slug, senha_atual, nova_senha)
                except Exception:
                    LOGGER.exception("Nao foi possivel alterar a senha da igreja.")
                    st.error("Não foi possível alterar a senha. Tente novamente.")
                else:
                    if alterada:
                        _encerrar_sessao()
                        st.success("Senha alterada. Entre novamente com a nova senha.")
                        st.rerun()
                    else:
                        st.error("Senha atual incorreta.")
