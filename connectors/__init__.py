"""
connectors/  -  Los dos sistemas de registro del operating model, como conectores
de SOLO LECTURA.

El diagrama del operating model abre con dos fuentes que no se hablan entre si:
Salesforce (fondeo) y NetSuite (contable). Aca dejan de ser una etiqueta y pasan a
ser el camino de lectura real: cada acceso pasa por governance.assert_read_only, la
PII vive (y se queda) en el conector de Salesforce, y la capa de orquestacion
reconcilia lo que cada sistema reporta.

  - netsuite.py    contable: caja, gasto, fondos, AP, ingreso de donaciones en el GL.
  - salesforce.py  fondeo: donantes, donaciones reconocidas, AR, campanias, voluntarios.
                   Es el unico lugar donde existe la PII de donantes (email, telefono,
                   contacto); no entra nunca al estado compartido ni a una salida.

Los datos sinteticos viven en finance_core_potenciar._backing_store (el stand-in de
las bases productivas). Los conectores son la interfaz de lectura sobre esa fuente.
"""
