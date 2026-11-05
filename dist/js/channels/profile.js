document.addEventListener('DOMContentLoaded', function () {
  let websocket = new WebSocket('wss://' + window.location.host + '/ws/user/');
  websocket.onopen = function () {
    console.log('Connected');
  };

  websocket.onmessage = function () {
    console.log('Messaged');
  };

  websocket.onclose = function () {
    console.log('Closed');
  };

  websocket.onerror = function () {
    console.log('Error!');
  };
});
