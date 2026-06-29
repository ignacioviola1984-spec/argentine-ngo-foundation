# Rúbrica de revisión - entregables del operating model

La rúbrica con la que el consultor (HITL) firma cada entregable, y contra la que
se evalúan los *golden outputs*. Es un activo de IA versionado: se reutiliza al
escalar a otra ONG.

## Reglas duras (si una falla, el entregable no se firma)

1. **Todo número viene del código.** Ninguna cifra de la narrativa puede faltar en
   el payload determinístico del entregable (`datos`). El guarda de grounding de
   `llm.py` lo hace cumplir; la revisión lo confirma.
2. **Sin PII en una salida publicable.** El reporte y los dashboards no mencionan
   nombres de donantes ni datos de contacto. La PII se queda en Salesforce.
3. **Fail-closed.** Si un control determinístico (gate) no cuadra, el entregable
   queda bloqueado. No se firma un número sobre un control que falla.
4. **Honestidad de cobertura.** Una ONG con un solo sistema recibe indicadores
   parciales marcados como tales, nunca un número inventado para tapar el sistema
   que falta.
5. **Solo lectura.** Nada del pipeline escribe en NetSuite ni en Salesforce.

## Criterios de calidad (juicio del revisor)

- **Verdict-first:** la narrativa abre con la conclusión (runway, ejecución, estado
  del cierre), no con el contexto.
- **Sobriedad:** sin superlativos ni afirmaciones que el dato no respalde.
- **Trazable:** el entregable referencia el período y el nivel de dato de la ONG.
- **Accionable:** si hay una escalación, dice qué se sugiere hacer.

## Firma

El revisor aprueba, edita o rechaza. La firma queda en la traza append-only
(`audit_log.jsonl`) con revisor, nota y timestamp. El reporte, además, pasa por el
gate final de publicación (nivel 2) antes de salir hacia Comisión Directiva y
donantes.
