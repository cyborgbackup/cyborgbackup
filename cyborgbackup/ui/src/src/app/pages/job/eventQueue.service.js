(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.job')
      .service('eventQueue', eventQueue);

/** @ngInject */
function eventQueue(jobResults, parseStdout){
      var val = {};

      val = {
          populateDefers: {},
          queue: {},
          // munge the raw event from the backend into the event_queue's format
          munge: function(event) {
              // basic data needed in the munged event
              var mungedEvent = {
                  counter: event.counter,
                  id: event.id,
                  processed: false,
                  name: event.event_name,
                  changes: []
              };

              // the interface for grabbing standard out is generalized and
              // present across many types of events, so go ahead and check for
              // updates to it
              if (event.stdout) {
                  mungedEvent.stdout = parseStdout.parseStdout(event);
                  mungedEvent.start_line = event.start_line + 1;
                  mungedEvent.end_line = event.end_line + 1;
                  mungedEvent.actual_end_line = parseStdout.actualEndLine(event) + 1;
                  mungedEvent.changes.push('stdout');
              }

              return mungedEvent;
          },
          // reinitializes the event queue value for the job results page
          initialize: function() {
              val.queue = {};
              val.populateDefers = {};
          },
          // populates the event queue
          populate: function(event) {
              if (event) {
                  val.queue[event.counter] = val.munge(event);

                  if (!val.queue[event.counter].processed) {
                      return val.munge(event);
                  } else {
                      return {};
                  }
              } else {
                  return {};
              }
          },
          // the event has been processed in the view and should be marked as
          // completed in the queue
          markProcessed: function(event) {
              val.queue[event.counter].processed = true;
          }
      };

      return val;
  }
})();
