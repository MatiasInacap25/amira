# Mercado Pago Checkout Pro: pruebas en Chile

Este flujo solo cubre pagos de cotizaciones de clientes. Los reembolsos y pagos a prestadores siguen siendo simulados. No uses credenciales ni tarjetas reales.

## Preparación

1. En [Mercado Pago Developers](https://www.mercadopago.cl/developers/es/docs/checkout-pro-preferences/test-accounts?scope=prod), crea una aplicación para Chile y obtén sus credenciales de prueba y el identificador del vendedor de prueba. El prefijo del token por sí solo no demuestra que sea de prueba.
2. Configura el backend con `PAYMENT_PROVIDER=mercado_pago`, `MERCADO_PAGO_ACCESS_TOKEN` (token de prueba), `MERCADO_PAGO_TEST_SELLER_ID` (ID verificado del vendedor de prueba), `MERCADO_PAGO_WEBHOOK_SECRET` y `FRONTEND_BASE_URL` (URL pública del frontend para el retorno). Mantén los secretos fuera del repositorio y de los registros.
3. Configura las notificaciones de pago de Mercado Pago para que lleguen a la URL pública del backend con la ruta `/api/payments/mercado-pago/webhook`. Usa el secreto de firma correspondiente a esa configuración. Una URL local no es accesible para Mercado Pago sin una exposición pública autorizada.
4. Crea una cuenta de comprador de prueba de Chile distinta del vendedor. Consulta las instrucciones y tarjetas vigentes en [compras de prueba de Checkout Pro](https://www.mercadopago.cl/developers/es/docs/checkout-pro-preferences/integration-test/test-purchases). No pegues credenciales ni datos de tarjeta en el repositorio.

## Prueba

1. En una ventana privada, inicia sesión en Amira como cliente de una conversación con una cotización vigente y selecciona **Pagar**. Se abrirá el checkout de prueba de Mercado Pago.
2. Sigue la documentación oficial con el comprador y una tarjeta de prueba. Prueba los resultados disponibles de aprobación y rechazo; usa los datos de prueba proporcionados por Mercado Pago, nunca datos reales.
3. Al volver a Amira, comprueba que un pago aprobado confirma el servicio, uno rechazado muestra el fallo y uno pendiente muestra la espera. El retorno del navegador no confirma por sí solo el pago: el backend consulta al proveedor y también procesa notificaciones verificadas.
4. Si el pago se aprueba después de que la cotización vence o es reemplazada, el resultado debe mostrar **Pago en revisión**, sin afirmar que el servicio quedó confirmado. Si no llega una notificación, vuelve a consultar la página del resultado para activar la reconciliación.

Esta guía requiere credenciales y configuración de prueba reales; no implica que se haya ejecutado una compra contra Mercado Pago.
