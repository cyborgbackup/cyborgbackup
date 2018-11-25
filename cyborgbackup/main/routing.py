from channels.routing import route

channel_routing = [
    route("websocket.connect", "cyborgbackup.main.consumers.ws_connect", path=r'^/websocket/$'),
    route("websocket.disconnect", "cyborgbackup.main.consumers.ws_disconnect", path=r'^/websocket/$'),
    route("websocket.receive", "cyborgbackup.main.consumers.ws_receive", path=r'^/websocket/$'),
]
