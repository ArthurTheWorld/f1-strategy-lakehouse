# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

O público principal são recrutadores e engenheiros que avaliam Luiz Arthur, engenheiro de dados com 3 anos de experiência, para vagas de nível pleno. Essa pessoa chega por um link no portfólio ou no LinkedIn, tem poucos minutos e precisa julgar se o autor sabe construir e avaliar um sistema de dados de ponta a ponta. Nem todo visitante conhece Fórmula 1.

## Product Purpose

O F1 Strategy Lakehouse transforma dados de voltas de Fórmula 1 em análise de estratégia de corrida. O dashboard é a parte visível de um pipeline completo: camadas Bronze, Silver e Gold, modelo de tempo de volta, simulador de pit stop e detecção de anomalias.

O sucesso é o visitante entender em poucos minutos o que foi construído, ver que funciona com dados reais e sair confiando no critério técnico do autor.

## Positioning

Um lakehouse completo, com dbt e testes, que declara o que foi validado e o que não foi, mesmo quando o resultado é desfavorável. O diferencial não é o modelo mais preciso: é o rigor de construir o pipeline e avaliar o próprio trabalho com honestidade.

## Operating Context

- Acesso previsto por link público, a partir do portfólio (https://arthurtheworld.github.io) e do LinkedIn. A hospedagem ainda não foi publicada nem escolhida.
- O visitante percorre o dashboard por conta própria, sem demonstração guiada.
- Localmente, `rodar.ps1` baixa os dados, processa e abre o dashboard.

## Capabilities and Constraints

- Dashboard em Streamlit, somente leitura sobre Gold e `analytics.*` no DuckDB; o simulador recalcula estratégias a partir dos parâmetros do visitante.
- Abas: Corrida, Equipes, Degradação, Estratégia e Anomalias.
- O simulador compara estratégias em pista livre. Não simula tráfego, ultrapassagens, safety car nem clima.
- O modelo não extrapola além da idade de pneu com suporte nos dados.
- Terminologia: "voltas limpas" exclui volta 1, voltas de boxes e voltas sob bandeira ou safety car.
- Em aberto: onde publicar o dashboard.

## Brand Commitments

- Nome: F1 Strategy Lakehouse. Interface em português do Brasil.
- Sem logos, marcas ou modelos oficiais de equipes de Fórmula 1. Equipes aparecem apenas por nome e cor.
- Quando os dados forem sintéticos, o dashboard precisa dizer isso de forma explícita.
- Decisão visual do autor (2026-11-09): tema Console da Hallmark, evitando aparência de produto feito por IA. Âmbar marca desvio e seleção; azul marca leitura de instrumento; vermelho, amarelo e branco ficam reservados aos pneus.
- A animação principal é um replay da corrida feito com dados reais. O carro desenhado aparece só na aba Equipes.

## Evidence on Hand

- Dados reais: 6 corridas de 2024 via FastF1 (Sakhir, Jeddah, Melbourne, Suzuka, Shanghai e Miami), em `data/f1.duckdb`.
- Avaliação sobre dados sintéticos com verdade conhecida: `docs/evaluation.json`.
- Resultado real (2026-11-10): com a volta da relargada de Suzuka fora do modelo, o XGBoost empata com a regressão linear (RMSE 0,99 contra 1,00, melhor em 4 de 6 corridas), em teste com uma corrida fora do treino.
- Limitação real conhecida: a recomendação do simulador é dominada pelo limite de idade do pneu e não reproduz o número de paradas observado.
- Não existem depoimentos, usuários, clientes, benchmarks externos ou métricas de uso. Nada disso pode ser inventado.

## Product Principles

1. **Mostrar a evidência junto da afirmação.** Todo resultado precisa deixar claro de onde veio e o que não prova.
2. **Limitações ficam à vista.** Um resultado ruim e bem explicado vale mais que um número bonito sem contexto.
3. **Entendível em poucos minutos.** Cada tela entrega a conclusão primeiro e o detalhe depois, inclusive para quem não acompanha F1.
4. **A engenharia é o produto.** O dashboard existe para tornar o pipeline e o critério do autor visíveis, não para substituí-los.
