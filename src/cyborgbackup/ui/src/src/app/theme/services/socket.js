(function (global, factory) {
    if (typeof define === 'function' && define.amd) {
        define([], factory);
    } else if (typeof module !== 'undefined' && module.exports){
        module.exports = factory();
    } else {
        global.ReconnectingWebSocket = factory();
    }
})(this, function () {

    if (!('WebSocket' in window)) {
        return;
    }

    function ReconnectingWebSocket(url, protocols, options) {

        // Default settings
        var settings = {

            /** Whether this instance should log debug messages. */
            debug: false,

            /** Whether or not the websocket should attempt to connect immediately upon instantiation. */
            automaticOpen: true,

            /** The number of milliseconds to delay before attempting to reconnect. */
            reconnectInterval: 1000,
            /** The maximum number of milliseconds to delay a reconnection attempt. */
            maxReconnectInterval: 30000,
            /** The rate of increase of the reconnect delay. Allows reconnect attempts to back off when problems persist. */
            reconnectDecay: 1.5,

            /** The maximum time in milliseconds to wait for a connection to succeed before closing and retrying. */
            timeoutInterval: 2000,

            /** The maximum number of reconnection attempts to make. Unlimited if null. */
            maxReconnectAttempts: null,

            /** The binary type, possible values 'blob' or 'arraybuffer', default 'blob'. */
            binaryType: 'blob'
        }
        if (!options) { options = {}; }

        // Overwrite and define settings with options if they exist.
        for (var key in settings) {
            if (typeof options[key] !== 'undefined') {
                this[key] = options[key];
            } else {
                this[key] = settings[key];
            }
        }

        // These should be treated as read-only properties

        /** The URL as resolved by the constructor. This is always an absolute URL. Read only. */
        this.url = url;

        /** The number of attempted reconnects since starting, or the last successful connection. Read only. */
        this.reconnectAttempts = 0;

        /**
         * The current state of the connection.
         * Can be one of: WebSocket.CONNECTING, WebSocket.OPEN, WebSocket.CLOSING, WebSocket.CLOSED
         * Read only.
         */
        this.readyState = WebSocket.CONNECTING;

        /**
         * A string indicating the name of the sub-protocol the server selected; this will be one of
         * the strings specified in the protocols parameter when creating the WebSocket object.
         * Read only.
         */
        this.protocol = null;

        // Private state variables

        var self = this;
        var ws;
        var forcedClose = false;
        var timedOut = false;
        var eventTarget = document.createElement('div');

        // Wire up "on*" properties as event handlers

        eventTarget.addEventListener('open',       function(event) { self.onopen(event); });
        eventTarget.addEventListener('close',      function(event) { self.onclose(event); });
        eventTarget.addEventListener('connecting', function(event) { self.onconnecting(event); });
        eventTarget.addEventListener('message',    function(event) { self.onmessage(event); });
        eventTarget.addEventListener('error',      function(event) { self.onerror(event); });

        // Expose the API required by EventTarget

        this.addEventListener = eventTarget.addEventListener.bind(eventTarget);
        this.removeEventListener = eventTarget.removeEventListener.bind(eventTarget);
        this.dispatchEvent = eventTarget.dispatchEvent.bind(eventTarget);

        /**
         * This function generates an event that is compatible with standard
         * compliant browsers and IE9 - IE11
         *
         * This will prevent the error:
         * Object doesn't support this action
         *
         * http://stackoverflow.com/questions/19345392/why-arent-my-parameters-getting-passed-through-to-a-dispatched-event/19345563#19345563
         * @param s String The name that the event should use
         * @param args Object an optional object that the event will use
         */
        function generateEvent(s, args) {
        	var evt = document.createEvent("CustomEvent");
        	evt.initCustomEvent(s, false, false, args);
        	return evt;
        };

        this.open = function (reconnectAttempt) {
            ws = new WebSocket(self.url, protocols || []);
            ws.binaryType = this.binaryType;

            if (reconnectAttempt) {
                if (this.maxReconnectAttempts && this.reconnectAttempts > this.maxReconnectAttempts) {
                    return;
                }
            } else {
                eventTarget.dispatchEvent(generateEvent('connecting'));
                this.reconnectAttempts = 0;
            }

            if (self.debug || ReconnectingWebSocket.debugAll) {
                console.debug('ReconnectingWebSocket', 'attempt-connect', self.url);
            }

            var localWs = ws;
            var timeout = setTimeout(function() {
                if (self.debug || ReconnectingWebSocket.debugAll) {
                    console.debug('ReconnectingWebSocket', 'connection-timeout', self.url);
                }
                timedOut = true;
                localWs.close();
                timedOut = false;
            }, self.timeoutInterval);

            ws.onopen = function(event) {
                clearTimeout(timeout);
                if (self.debug || ReconnectingWebSocket.debugAll) {
                    console.debug('ReconnectingWebSocket', 'onopen', self.url);
                }
                self.protocol = ws.protocol;
                self.readyState = WebSocket.OPEN;
                self.reconnectAttempts = 0;
                var e = generateEvent('open');
                e.isReconnect = reconnectAttempt;
                reconnectAttempt = false;
                eventTarget.dispatchEvent(e);
            };

            ws.onclose = function(event) {
                clearTimeout(timeout);
                ws = null;
                if (forcedClose) {
                    self.readyState = WebSocket.CLOSED;
                    eventTarget.dispatchEvent(generateEvent('close'));
                } else {
                    self.readyState = WebSocket.CONNECTING;
                    var e = generateEvent('connecting');
                    e.code = event.code;
                    e.reason = event.reason;
                    e.wasClean = event.wasClean;
                    eventTarget.dispatchEvent(e);
                    if (!reconnectAttempt && !timedOut) {
                        if (self.debug || ReconnectingWebSocket.debugAll) {
                            console.debug('ReconnectingWebSocket', 'onclose', self.url);
                        }
                        eventTarget.dispatchEvent(generateEvent('close'));
                    }

                    var timeout = self.reconnectInterval * Math.pow(self.reconnectDecay, self.reconnectAttempts);
                    setTimeout(function() {
                        self.reconnectAttempts++;
                        self.open(true);
                    }, timeout > self.maxReconnectInterval ? self.maxReconnectInterval : timeout);
                }
            };
            ws.onmessage = function(event) {
                if (self.debug || ReconnectingWebSocket.debugAll) {
                    console.debug('ReconnectingWebSocket', 'onmessage', self.url, event.data);
                }
                var e = generateEvent('message');
                e.data = event.data;
                eventTarget.dispatchEvent(e);
            };
            ws.onerror = function(event) {
                if (self.debug || ReconnectingWebSocket.debugAll) {
                    console.debug('ReconnectingWebSocket', 'onerror', self.url, event);
                }
                eventTarget.dispatchEvent(generateEvent('error'));
            };
        }

        // Whether or not to create a websocket upon instantiation
        if (this.automaticOpen == true) {
            this.open(false);
        }

        /**
         * Transmits data to the server over the WebSocket connection.
         *
         * @param data a text string, ArrayBuffer or Blob to send to the server.
         */
        this.send = function(data) {
            if (ws) {
                if (self.debug || ReconnectingWebSocket.debugAll) {
                    console.debug('ReconnectingWebSocket', 'send', self.url, data);
                }
                return ws.send(data);
            } else {
                throw 'INVALID_STATE_ERR : Pausing to reconnect websocket';
            }
        };

        /**
         * Closes the WebSocket connection or connection attempt, if any.
         * If the connection is already CLOSED, this method does nothing.
         */
        this.close = function(code, reason) {
            // Default CLOSE_NORMAL code
            if (typeof code == 'undefined') {
                code = 1000;
            }
            forcedClose = true;
            if (ws) {
                ws.close(code, reason);
            }
        };

        /**
         * Additional public API method to refresh the connection if still open (close, re-open).
         * For example, if the app suspects bad data / missed heart beats, it can try to refresh.
         */
        this.refresh = function() {
            if (ws) {
                ws.close();
            }
        };
    }

    /**
     * An event listener to be called when the WebSocket connection's readyState changes to OPEN;
     * this indicates that the connection is ready to send and receive data.
     */
    ReconnectingWebSocket.prototype.onopen = function(event) {};
    /** An event listener to be called when the WebSocket connection's readyState changes to CLOSED. */
    ReconnectingWebSocket.prototype.onclose = function(event) {};
    /** An event listener to be called when a connection begins being attempted. */
    ReconnectingWebSocket.prototype.onconnecting = function(event) {};
    /** An event listener to be called when a message is received from the server. */
    ReconnectingWebSocket.prototype.onmessage = function(event) {};
    /** An event listener to be called when an error occurs. */
    ReconnectingWebSocket.prototype.onerror = function(event) {};

    /**
     * Whether all instances of ReconnectingWebSocket should log debug messages.
     * Setting this to true is the equivalent of setting all instances of ReconnectingWebSocket.debug to true.
     */
    ReconnectingWebSocket.debugAll = false;

    ReconnectingWebSocket.CONNECTING = WebSocket.CONNECTING;
    ReconnectingWebSocket.OPEN = WebSocket.OPEN;
    ReconnectingWebSocket.CLOSING = WebSocket.CLOSING;
    ReconnectingWebSocket.CLOSED = WebSocket.CLOSED;

    return ReconnectingWebSocket;
});

(function () {
  'use strict';

  angular.module('CyBorgBackup.theme')
      .service('SocketService', SocketService);

  /** @ngInject */
  function SocketService($rootScope, $location, $log, $state, $q) {
      var needsResubscribing = false,
      socketPromise = $q.defer();
      return {
          init: function() {
              var self = this,
                  host = window.location.host,
                  protocol,
                  url;

              if($location.protocol() === 'http'){
                  protocol = 'ws';
              }
              if($location.protocol() === 'https'){
                  protocol = 'wss';
              }
              url = protocol+'://'+host+'/websocket/';

              if (!$rootScope.sessionTimer || ($rootScope.sessionTimer && !$rootScope.sessionTimer.isExpired())) {

                  $log.debug('Socket connecting to: ' + url);
                  self.socket = new ReconnectingWebSocket(url, null, {
                      timeoutInterval: 3000,
                      maxReconnectAttempts: 10                    });

                  self.socket.onopen = function () {
                      $log.debug("Websocket connection opened. Socket readyState: " + self.socket.readyState);
                      socketPromise.resolve();
                      self.checkStatus();
                      if(needsResubscribing){
                          self.subscribe(self.getLast());
                          needsResubscribing = false;
                      }

                  };

                  self.socket.onerror = function (error) {
                      self.checkStatus();
                      $log.debug('Websocket Error Logged: ' + error); //log errors
                  };

                  self.socket.onconnecting = function () {
                      self.checkStatus();
                      $log.debug('Websocket reconnecting');
                      needsResubscribing = true;
                  };

                  self.socket.onclose = function () {
                      self.checkStatus();
                      $log.debug('Websocket disconnected');
                  };

                  self.socket.onmessage = this.onMessage;

                  return self.socket;
              }
              else {
                  // encountered expired token, redirect to login page
                  $rootScope.sessionTimer.expireSession('idle');
                  $location.url('/login');
              }
          },
          onMessage: function(e){
              // Function called when messages are received on by the UI from
              // the API over the websocket. This will route each message to
              // the appropriate controller for the current $state.
              $log.debug('Received From Server: ' + e.data);

              var data = JSON.parse(e.data), str = "";
              if(data.group_name==="jobs" && !('status' in data)){
                  // we know that this must have been a
                  // summary complete message b/c status is missing.
                  // A an object w/ group_name === "jobs" AND a 'status' key
                  // means it was for the event: status_changed.
                  $log.debug('Job summary_complete ' + data.job_id);
                  $rootScope.$broadcast('ws-jobs-summary', data);
                  return;
              }
              else if(data.group_name==="job_events"){
                  // The naming scheme is "ws" then a
                  // dash (-) and the group_name, then the job ID
                  // ex: 'ws-jobs-<jobId>'
                  str = 'ws-'+data.group_name+'-'+data.job;
              }
              else if(data.group_name==="ad_hoc_command_events"){
                  // The naming scheme is "ws" then a
                  // dash (-) and the group_name, then the job ID
                  // ex: 'ws-jobs-<jobId>'
                  str = 'ws-'+data.group_name+'-'+data.ad_hoc_command;
              }
              else if(data.group_name==="control"){
                  // As of v. 3.1.0, there is only 1 "control"
                  // message, which is for expiring the session if the
                  // session limit is breached.
                  $log.debug(data.reason);
                  $rootScope.sessionTimer.expireSession('session_limit');
                  $state.go('signOut');
              }
              else {
                  // The naming scheme is "ws" then a
                  // dash (-) and the group_name.
                  // ex: 'ws-jobs'
                  str = 'ws-'+data.group_name;
              }
              $rootScope.$broadcast(str, data);
          },
          disconnect: function(){
              if(this.socket){
                  this.socket.close();
                  delete this.socket;
                  console.log("Socket deleted: "+this.socket);
              }
          },
          subscribe: function(state){
              // Subscribe is used to tell the API that the UI wants to
              // listen for specific messages. A subscription object could
              // look like {"groups":{"jobs": ["status_changed", "summary"]}.
              // This is used by all socket-enabled $states
              this.emit(JSON.stringify(state.data.socket));
              this.setLast(state);
          },
          unsubscribe: function(state){
              // Unsubscribing tells the API that the user is no longer on
              // on a socket-enabled page, and sends an empty groups object
              // to the API: {"groups": {}}.
              // This is used for all pages that are socket-disabled
              if(this.requiresNewSubscribe(state)){
                  this.emit(JSON.stringify(state.data.socket) || JSON.stringify({"groups": {}}));
              }
              this.setLast(state);
          },
          setLast: function(state){
              this.last = state;
          },
          getLast: function(){
              return this.last;
          },
          requiresNewSubscribe: function(state){
              // This function is used for unsubscribing. If the last $state
              // required an "unsubscribe", then we don't need to unsubscribe
              // again, b/c the UI is already unsubscribed from all groups
              if (this.getLast() !== undefined){
                  if( _.isEmpty(state.data.socket.groups) && _.isEmpty(this.getLast().data.socket.groups)){
                      return false;
                  }
                  else {
                      return true;
                  }
              }
              else {
                  return true;
              }
          },
          checkStatus: function() {
              // Function for changing the socket indicator icon in the nav bar
              var self = this;
              if(self){
                  if(self.socket){
                      if (self.socket.readyState === 0 ) {
                          $rootScope.socketStatus = 'connecting';
                          $rootScope.socketTip = 'Live events: attempting to connect to the '+$rootScope.BRAND_NAME+ 'server.';
                      }
                      else if (self.socket.readyState === 1){
                          $rootScope.socketStatus = 'ok';
                          $rootScope.socketTip = "Live events: connected. Pages containing job status information will automatically update in real-time.";
                      }
                      else if (self.socket.readyState === 2 || self.socket.readyState === 3 ){
                          $rootScope.socketStatus = 'error';
                          $rootScope.socketTip = 'Live events: error connecting to the '+$rootScope.BRAND_NAME+' server.';
                      }
                      return;
                  }
              }

          },
          emit: function(data, callback) {
              // Function used for sending objects to the API over the
              // websocket.
              var self = this;
              socketPromise.promise.then(function(){
                  if(self.socket.readyState === 0){
                      $log.debug('Unable to send message, waiting 500ms to resend. Socket readyState: ' + self.socket.readyState);
                      setTimeout(function(){
                          self.subscribe(self.getLast());
                      }, 500);
                  }
                  else if(self.socket.readyState === 1){
                      self.socket.send(data, function () {
                          var args = arguments;
                          self.scope.$apply(function () {
                              if (callback) {
                                  callback.apply(self.socket, args);
                              }
                          });
                      });
                      $log.debug('Sent to Websocket Server: ' + data);
                  }
              });
          },
          addStateResolve: function(state, id){
              // This function is used for add a state resolve to all states,
              // socket-enabled AND socket-disabled, and whether the $state
              // requires a subscribe or an unsubscribe
              var self = this;
              socketPromise.promise.then(function(){
                  if(!state.data || !state.data.socket){
                      _.merge(state.data, {socket: {groups: {}}});
                      self.unsubscribe(state);
                  }
                  else{
                      ["job_events", "ad_hoc_command_events", "workflow_events",
                       "project_update_events", "inventory_update_events",
                       "system_job_events"
                      ].forEach(function(group) {
                          if(state.data && state.data.socket && state.data.socket.groups.hasOwnProperty(group)){
                              state.data.socket.groups[group] = [id];
                          }
                      });
                      self.subscribe(state);
                  }
                  return true;
              });
          }
      };
  }
})();
