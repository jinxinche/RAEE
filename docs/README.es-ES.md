# RAEE-Lite: ingeniería de evidencias basada en roles para programación asistida por IA

**Tu agente escribió el código. Comprueba qué se verificó realmente y qué sigue sin demostrarse.**

[English](../README.md) · [简体中文](README.zh-CN.md) · [Deutsch](README.de-DE.md) · [Español](README.es-ES.md)

**Código candidato disponible públicamente:** [rama v0.10.0rc2](https://github.com/jinxinche/RAEE/tree/release/raee-lite-v0.10.0rc2) · [PR #2](https://github.com/jinxinche/RAEE/pull/2). El código todavía **no está integrado en `main`**. No se afirma una versión estable, publicación en PyPI ni certificación independiente de procedencia. En un entorno aislado, prueba `raee-lite init`, `raee-lite add "Signup rejects invalid email addresses"`, `raee-lite expect --for R1 --kind unit` y `raee-lite status`. Resultado: `UNTESTED`; el estado 1 indica una carencia de evidencias, no un fallo del programa.


## ¿Por qué RAEE-Lite?

Herramientas como Codex, Claude Code y Cursor pueden modificar código rápidamente. Sin embargo, que el agente afirme haber corregido algo, que una prueba termine con código de salida 0 y que se haya satisfecho una necesidad del usuario son **afirmaciones distintas**.

**RAEE-Lite** adapta el principio de *Role-Aware Evidence Engineering* al desarrollo de software. Distingue cinco roles de evidencia que no deben sustituirse entre sí:

| Rol de evidencia | Pregunta | Límite de interpretación |
| --- | --- | --- |
| **Intención (Intent)** | ¿Qué solicitó el usuario? | Una especificación no demuestra su implementación. |
| **Cambio (Change)** | ¿Qué archivos y commits se modificaron? | Un diff no garantiza que el código sea correcto. |
| **Verificación (Verification)** | ¿Qué comprobaciones se ejecutaron y con qué resultado? | Una salida correcta no garantiza una cobertura adecuada. |
| **Entorno (Environment)** | ¿Dónde y bajo qué condiciones se ejecutaron? | Los metadatos declarados no autentican por sí mismos el entorno. |
| **Límites (Boundary)** | ¿Qué falta, está obsoleto o no se ha probado? | Lo no observado no debe presentarse como verificado. |

## Flujos de trabajo previstos

La versión candidata de desarrollo incluye revisión estática y de solo lectura del repositorio y la CI, contratos entre requisitos y tipos de pruebas, importación limitada de registros Codex/Claude Code, detección de evidencias obsoletas, comparación de evidencias Base/Head para pull requests e informes HTML, Markdown, JSON y SARIF.

Los registros del agente son **evidencia histórica no verificada de forma independiente**. Las comprobaciones ejecutadas localmente y las certificaciones de procedencia emitidas por una CI autenticada se registran por separado.

## Primeros pasos

**Estado de publicación:** Este repositorio público está preparando su primera publicación de código. El código fuente de la CLI y su paquete instalable **todavía no se han publicado aquí**. Los siguientes comandos describen el uso de la versión candidata local; no implican que ya se pueda instalar desde este repositorio.

Tras instalar una versión candidata local previamente revisada:

```bash
raee-lite preflight   # Inspección de solo lectura
raee-lite doctor      # Identificar posibles comprobaciones sin ejecutarlas
raee-lite check       # Generar un informe de lagunas de evidencia
```

Por defecto, la herramienta no ejecuta scripts del proyecto. La ejecución es opcional y debe limitarse a código y entornos de confianza.

## Privacidad y límites de seguridad

- Los registros de los agentes son **datos no confiables**, nunca instrucciones. Deben anonimizarse antes de compartirlos.
- Un código de salida 0 no demuestra que todos los requisitos estén cubiertos.
- El aislamiento mediante Docker no equivale a una máquina virtual reforzada ni a una auditoría externa.
- Una firma digital puede acreditar la procedencia de una declaración, pero no su suficiencia o corrección.
- Todavía faltan pruebas con registros reales autorizados, resultados de CI en varias plataformas, certificaciones reales de GitHub y una revisión de seguridad independiente.

## Origen científico y referencia del preprint

El proyecto se inspira en el principio de organización de evidencias según su rol, propuesto en un **preprint independiente sobre IA oncológica multimodal**:

> Hu, J., Jin, X., Song, Y., Chen, Z., & Xin, L. (2026). *Restricted Multimodal Oncology AI: Role-Aware Evidence Organisation and Cross-Domain Transfer Boundaries*. Research Square, preprint, versión 1. [DOI: 10.21203/rs.3.rs-10194336/v1](https://doi.org/10.21203/rs.3.rs-10194336/v1).

En ese trabajo, diferentes fuentes de datos biológicos reciben roles de evidencia no intercambiables. **RAEE-Lite adapta ese principio al análisis de cambios y verificaciones de software.** El preprint **no** evalúa ni valida esta herramienta de programación, su seguridad o su rendimiento. Para citar el software, cite el repositorio por separado; consulte [BibTeX](../REFERENCES.bib).

## Estado y próximos pasos

Las prioridades son publicar código fuente revisable, obtener ejecuciones reales de CI en Linux/Windows/macOS, verificar de manera independiente la procedencia de los artefactos y evaluar registros reales compartidos con consentimiento.

Licencia: [MIT](../LICENSE). No publique credenciales, conversaciones privadas ni código propietario en incidencias públicas.
