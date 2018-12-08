(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.job')
    .controller('JobDetailCtrl', JobDetailCtrl);

  /** @ngInject */
  function JobDetailCtrl($rootScope, $scope, $compile, $filter, $uibModal, $stateParams, $state, $interpolate, $q,
      toastr, timerService, statusSocket, jobData, jobDataOptions, jobFinished, eventQueue, parseStdout,
       jobResults, Dataset, Prompt, Wait, Rest, ProcessErrors, GetBasePath, QuerySet) {
    var toDestroy = [];
    var cancelRequests = false;
    var runTimeElapsedTimer = null;

    // download stdout tooltip text
    $scope.standardOutTooltip = 'Download Output';

    // stdout full screen toggle tooltip text
    $scope.toggleStdoutFullscreenTooltip = "Expand Output";

    // this allows you to manage the timing of rest-call based events as
    // filters are updated.  see processPage for more info
    var currentContext = 1;
    $scope.firstCounterFromSocket = -1;

    $scope.explanationLimit = 150;

    // if the user enters the page mid-run, reset the search to include a param
    // to only grab events less than the first counter from the websocket events
    toDestroy.push($scope.$watch('firstCounterFromSocket', function(counter) {
        if (counter > -1) {
            // make it so that the search include a counter less than the
            // first counter from the socket
            let params = _.cloneDeep($stateParams.job_event_search);
            params.counter__lte = "" + counter;

            Dataset = QuerySet.search(jobData.related.job_events,
                params);

            Dataset.then(function(actualDataset) {
                $scope.job_event_dataset = actualDataset.data;
            });
        }
    }));

    // used for tag search
    $scope.job_event_dataset = Dataset.data;

    // used for tag search
    $scope.list = {
        basePath: jobData.related.job_events,
        name: 'job_events'
    };

    // used for tag search
    $scope.job_events = $scope.job_event_dataset.results;

    var getLinks = function() {
        var getLink = function(key) {
            if ($scope.job.related[key]) {
                return '/#/' + $scope.job.related[key]
                    .split(/api\/v\d+\//)[1];
            } else {
                return null;
            }
        };

        $scope.created_by_link = getLink('created_by');
    };

    // uses options to set scope variables to their readable string
    // value
    var getLabels = function() {
        var getLabel = function(key) {
            if ($scope.jobOptions && $scope.jobOptions[key]) {
                return $scope.jobOptions[key].choices
                    .filter(val => val[0] === $scope.job[key])
                    .map(val => val[1])[0];
            } else {
                return null;
            }
        };

        $scope.type_label = getLabel('job_type');
    };

    // put initially resolved request data on scope
    $scope.job = jobData;
    $scope.jobOptions = jobDataOptions.actions.GET;
    $scope.jobFinished = jobFinished;

    // update label in left pane and tooltip in right pane when the job_status
    // changes
    toDestroy.push($scope.$watch('job_status', function(status) {
        if (status) {
            $scope.status_label = $scope.jobOptions.status.choices
                .filter(val => val[0] === status)
                .map(val => val[1])[0];
            $scope.status_tooltip = "Job " + $scope.status_label;
        }
    }));

    $scope.previousTaskFailed = false;

    toDestroy.push($scope.$watch('job.job_explanation', function(explanation) {
        if (explanation && explanation.split(":")[0] === "Previous Task Failed") {
            $scope.previousTaskFailed = true;

            var taskObj = JSON.parse(explanation.substring(explanation.split(":")[0].length + 1));
            $scope.explanation_fail_type = taskObj.job_type;
            $scope.explanation_fail_name = taskObj.job_name;
            $scope.explanation_fail_id = taskObj.job_id;
            $scope.task_detail = $scope.explanation_fail_type + " failed for " + $scope.explanation_fail_name + " with ID " + $scope.explanation_fail_id + ".";
        } else {
            $scope.previousTaskFailed = false;
        }
    }));


    // update the job_status value.  Use the cached rootScope value if there
    // is one.  This is a workaround when the rest call for the jobData is
    // made before some socket events come in for the job status
    if ($rootScope['lastSocketStatus' + jobData.id]) {
        $scope.job_status = $rootScope['lastSocketStatus' + jobData.id];
        delete $rootScope['lastSocketStatus' + jobData.id];
    } else {
        $scope.job_status = jobData.status;
    }

    // turn related api browser routes into front end routes
    getLinks();

    // the links below can't be set in getLinks because the
    // links on the UI don't directly match the corresponding URL
    // on the API browser
    if(jobData.result_traceback) {
        $scope.job.result_traceback = jobData.result_traceback.trim().split('\n').join('<br />');
    }

    getLabels();

    // Click binding for the expand/collapse button on the standard out log
    $scope.stdoutFullScreen = false;
    $scope.toggleStdoutFullscreen = function() {
        $scope.stdoutFullScreen = !$scope.stdoutFullScreen;

        if ($scope.stdoutFullScreen === true) {
            $scope.toggleStdoutFullscreenTooltip = "Collapse Output";
        } else if ($scope.stdoutFullScreen === false) {
            $scope.toggleStdoutFullscreenTooltip = "Expand Output";
        }
    };

    $scope.deleteJob = function() {
        jobResults.deleteJob($scope.job);
    };

    $scope.cancelJob = function() {
        jobResults.cancelJob($scope.job);
    };

    $scope.relaunchJob = function() {
        req = {
            method: 'POST',
            url: `${$scope.job.url}/relaunch/`
        };

        $http(req).then((launchRes) => {
            if (!$state.includes('job')) {
                $state.go('jobResult', { id: launchRes.data.id }, { reload: true });
            }
        });
    };

    // if the job is still running engage following of the last line in the
    // standard out pane
    $scope.followEngaged = !$scope.jobFinished;

    // follow button for completed job should specify that the
    // button will jump to the bottom of the standard out pane,
    // not follow lines as they come in
    if ($scope.jobFinished) {
        $scope.followTooltip = "Jump to last line of standard out.";
    } else {
        $scope.followTooltip = "Currently following standard out as it comes in.  Click to unfollow.";
    }

    $scope.events = {};

    function updateJobElapsedTimer(time) {
        $scope.job.elapsed = time;
    }

    // For elapsed time while a job is running, compute the differnce in seconds,
    // from the time the job started until now. Moment() returns the current
    // time as a moment object.
    if ($scope.job.started !== null && $scope.job.status === 'running') {
        runTimeElapsedTimer = timerService.createOneSecondTimer($scope.job.started, updateJobElapsedTimer);
    }

    // EVENT STUFF BELOW
    var linesInPane = [];

    function addToLinesInPane(event) {
        var arr = _.range(event.start_line, event.actual_end_line);
        linesInPane = linesInPane.concat(arr);
        linesInPane = linesInPane.sort(function(a, b) {
            return a - b;
        });
    }

    function appendToBottom (event){
        // if we get here then the event type was either a
        // header line, recap line, or one of the additional
        // event types, so we append it to the bottom.
        // These are the event types for captured
        // stdout not directly related to playbook or runner
        // events:
        // (0, 'debug', _('Debug'), False),
        // (0, 'verbose', _('Verbose'), False),
        // (0, 'deprecated', _('Deprecated'), False),
        // (0, 'warning', _('Warning'), False),
        // (0, 'system_warning', _('System Warning'), False),
        // (0, 'error', _('Error'), True),
        angular
            .element(".JobResultsStdOut-stdoutContainer")
            .append($compile(event
                .stdout)($scope.events[event
                    .counter]));
    }

    function putInCorrectPlace(event) {
        if (linesInPane.length) {
            for (var i = linesInPane.length - 1; i >= 0; i--) {
                if (event.start_line > linesInPane[i]) {
                    $(`.line_num_${linesInPane[i]}`)
                        .after($compile(event
                            .stdout)($scope.events[event
                                .counter]));
                    i = -1;
                }
            }
        } else {
            appendToBottom(event);
        }
    }

    // This is where the async updates to the UI actually happen.
    // Flow is event queue munging in the service -> $scope setting in here
    var processEvent = function(event, context) {
        // only care about filter context checking when the event comes
        // as a rest call
        if (context && context !== currentContext) {
            return;
        }
        // put the event in the queue
        var mungedEvent = eventQueue.populate(event);

        // make changes to ui based on the event returned from the queue
        if (mungedEvent.changes) {
            mungedEvent.changes.forEach(change => {
                // we've got a change we need to make to the UI!
                // update the necessary scope and make the change
                if (change === 'startTime' && !$scope.job.start) {
                    $scope.job.start = mungedEvent.startTime;
                }

                if (change === 'finishedTime'  && !$scope.job.finished) {
                    $scope.job.finished = mungedEvent.finishedTime;
                    $scope.jobFinished = true;
                    $scope.followTooltip = "Jump to last line of standard out.";
                    if ($scope.followEngaged) {
                        if (!$scope.followScroll) {
                            $scope.followScroll = function() {
                                $log.error("follow scroll undefined, standard out directive not loaded yet?");
                            };
                        }
                        $scope.followScroll();
                    }
                }


                if(change === 'stdout'){
                    if (!$scope.events[mungedEvent.counter]) {
                        // line hasn't been put in the pane yet

                        // create new child scope
                        $scope.events[mungedEvent.counter] = $scope.$new();
                        $scope.events[mungedEvent.counter]
                            .event = mungedEvent;

                        // let's see if we have a specific place to put it in
                        // the pane
                        let $prevElem = $(`.next_is_${mungedEvent.start_line}`);
                        if ($prevElem && $prevElem.length) {
                            // if so, put it there
                            $(`.next_is_${mungedEvent.start_line}`)
                                .after($compile(mungedEvent
                                    .stdout)($scope.events[mungedEvent
                                        .counter]));
                            addToLinesInPane(mungedEvent);
                        } else {
                            var putIn;
                            var classList = $("div",
                                "<div>"+mungedEvent.stdout+"</div>")
                                .attr("class").split(" ");
                            if (classList
                                .filter(v => v.indexOf("task_") > -1)
                                .length) {
                                putIn = classList
                                    .filter(v => v.indexOf("task_") > -1)[0];
                            } else if(classList
                                .filter(v => v.indexOf("play_") > -1)
                                .length) {
                                putIn = classList
                                    .filter(v => v.indexOf("play_") > -1)[0];
                            }

                            var putAfter;
                            var isDup = false;

                            if ($(".header_" + putIn + ",." + putIn).length === 0) {
                                putInCorrectPlace(mungedEvent);
                                addToLinesInPane(mungedEvent);
                            } else {
                                $(".header_" + putIn + ",." + putIn)
                                    .each((i, v) => {
                                        if (angular.element(v).scope()
                                            .event.start_line < mungedEvent
                                            .start_line) {
                                                putAfter = v;
                                        } else if (angular.element(v).scope()
                                            .event.start_line === mungedEvent
                                            .start_line) {
                                                isDup = true;
                                                return false;
                                        } else if (angular.element(v).scope()
                                            .event.start_line > mungedEvent
                                            .start_line) {
                                                return false;
                                        }  else {
                                            appendToBottom(mungedEvent);
                                            addToLinesInPane(mungedEvent);
                                        }
                                    });
                            }

                            if (!isDup && putAfter) {
                                addToLinesInPane(mungedEvent);
                                $(putAfter).after($compile(mungedEvent
                                    .stdout)($scope.events[mungedEvent
                                        .counter]));
                            }


                            classList = null;
                            putIn = null;
                        }

                        // delete ref to the elem because it might leak scope
                        // if you don't
                        $prevElem = null;
                    }

                    // move the followAnchor to the bottom of the
                    // container
                    $(".JobResultsStdOut-followAnchor")
                        .appendTo(".JobResultsStdOut-stdoutContainer");
                }
            });

            // the changes have been processed in the ui, mark it in the
            // queue
            eventQueue.markProcessed(event);
        }
    };

    $scope.stdoutContainerAvailable = $q.defer();
    $scope.hasSkeleton = $q.defer();

    eventQueue.initialize();

    // get header and recap lines
    var getSkeleton = function(url) {
        jobResults.getEvents(url)
            .then(events => {
                events.results.forEach(event => {
                    // get the name in the same format as the data
                    // coming over the websocket
                    event.event_name = event.event;
                    delete event.event;

                    processEvent(event);
                });
                if (events.next) {
                    getSkeleton(events.next);
                } else {
                    // after the skeleton requests have completed,
                    // put the play and task count into the dom
                    //$scope.playCount = skeletonPlayCount;
                    //$scope.taskCount = skeletonTaskCount;
                    $scope.hasSkeleton.resolve("skeleton resolved");
                }
            });
    };

    $scope.stdoutContainerAvailable.promise.then(() => {
        getSkeleton(jobData.related.job_events + "?order_by=start_line");
    });

    var getEvents;

    var processPage = function(events, context) {
        // currentContext is the context of the filter when this request
        // to processPage was made
        //
        // currentContext is the context of the filter currently
        //
        // if they are not the same, make sure to stop process events/
        // making rest calls for next pages/etc. (you can see context is
        // also passed into getEvents and processEvent and similar checks
        // exist in these functions)
        //
        // also, if the page doesn't contain results (i.e.: the response
        // returns an error), don't process the page
        if (context !== currentContext || events === undefined ||
            events.results === undefined) {
            return;
        }

        events.results.forEach(event => {
            // get the name in the same format as the data
            // coming over the websocket
            event.event_name = event.event;
            delete event.event;

            processEvent(event, context);
        });
        if (events.next && !cancelRequests) {
            getEvents(events.next, context);
        } else {
            // put those paused events into the pane
            $scope.gotPreviouslyRanEvents.resolve("");
        }
    };

    // grab non-header recap lines
    getEvents = function(url, context) {
        if (context !== currentContext) {
            return;
        }

        jobResults.getEvents(url)
            .then(events => {
                processPage(events, context);
            });
    };

    // grab non-header recap lines
    toDestroy.push($scope.$watch('job_event_dataset', function(val) {
        if (val) {
            eventQueue.initialize();

            Object.keys($scope.events)
                .forEach(v => {
                    // dont destroy scope events for skeleton lines
                    let name = $scope.events[v].event.name;
                });

            // pause websocket events from coming in to the pane
            $scope.gotPreviouslyRanEvents = $q.defer();
            currentContext += 1;

            let context = currentContext;

            $( ".JobResultsStdOut-aLineOfStdOut.not_skeleton" ).remove();
            $scope.hasSkeleton.promise.then(() => {
                if (val.count > parseInt(val.maxEvents)) {
                    //$(".header_task").hide();
                    //$(".header_play").hide();
                    $scope.standardOutTooltip = '<div class="JobResults-downloadTooLarge"><div>' +
                        'The output is too large to display. Please download.' +
                        '</div>' +
                        '<div class="JobResults-downloadTooLarge--icon">' +
                        '<span class="fa-stack fa-lg">' +
                        '<i class="fa fa-circle fa-stack-1x"></i>' +
                        '<i class="fa fa-stack-1x icon-job-stdout-download-tooltip"></i>' +
                        '</span>' +
                        '</div>' +
                        '</div>';

                    if ($scope.job_status === "successful" ||
                        $scope.job_status === "failed" ||
                        $scope.job_status === "error" ||
                        $scope.job_status === "canceled") {
                        $scope.tooManyEvents = true;
                        $scope.tooManyPastEvents = false;
                    } else {
                        $scope.tooManyPastEvents = true;
                        $scope.tooManyEvents = false;
                        $scope.gotPreviouslyRanEvents.resolve("");
                    }
                } else {
                    $(".header_task").show();
                    $(".header_play").show();
                    $scope.tooManyEvents = false;
                    $scope.tooManyPastEvents = false;
                    processPage(val, context);
                }
            });
        }
    }));

    var buffer = [];

    var processBuffer = function() {
        var follow = function() {
            // if follow is engaged,
            // scroll down to the followAnchor
            if ($scope.followEngaged) {
                if (!$scope.followScroll) {
                    $scope.followScroll = function() {
                        $log.error("follow scroll undefined, standard out directive not loaded yet?");
                    };
                }
                $scope.followScroll();
            }
        };

        for (let i = 0; i < 4; i++) {
            processEvent(buffer[i]);
            buffer.splice(i, 1);
        }

        follow();
    };

    var bufferInterval;

    // Processing of job_events messages from the websocket
    toDestroy.push($scope.$on(`ws-job_events-${$scope.job.id}`, function(e, data) {
        if (!bufferInterval) {
            bufferInterval = setInterval(function(){
                processBuffer();
            }, 500);
        }

        // use the lowest counter coming over the socket to retrigger pull data
        // to only be for stuff lower than that id
        //
        // only do this for entering the jobs page mid-run (thus the
        // data.counter is 1 conditional
        if (data.counter === 1) {
          $scope.firstCounterFromSocket = -2;
        }

        if ($scope.firstCounterFromSocket !== -2 &&
            $scope.firstCounterFromSocket === -1 ||
            data.counter < $scope.firstCounterFromSocket) {
                $scope.firstCounterFromSocket = data.counter;
        }

        $q.all([$scope.gotPreviouslyRanEvents.promise,
            $scope.hasSkeleton.promise]).then(() => {
            buffer.push(data);
        });
    }));

    // get previously set up socket messages from resolve
    if (statusSocket && statusSocket[0] && statusSocket[0].job_status) {
        $scope.job_status = statusSocket[0].job_status;
    }
    if ($scope.job_status === "running" && !$scope.job.elapsed) {
        runTimeElapsedTimer = timerService.createOneSecondTimer(moment(), updateJobElapsedTimer);
    }

    // Processing of job-status messages from the websocket
    toDestroy.push($scope.$on(`ws-jobs`, function(e, data) {
        if (parseInt(data.job_id, 10) ===
            parseInt($scope.job.id,10)) {
            // controller is defined, so set the job_status
            $scope.job_status = data.status;
            if (data.status === "running") {
                if (!runTimeElapsedTimer) {
                    runTimeElapsedTimer = timerService.createOneSecondTimer(moment(), updateJobElapsedTimer);
                }
            } else if (data.status === "successful" ||
                data.status === "failed" ||
                data.status === "error" ||
                data.status === "canceled") {
                    timerService.destroyTimer(runTimeElapsedTimer);

                    // When the fob is finished retrieve the job data to
                    // correct anything that was out of sync from the job run
                    jobResults.getJobData($scope.job.id).then(function(data){
                        $scope.job = data;
                        $scope.jobFinished = true;
                    });
            }
        } else {
            // controller was previously defined, but is not yet defined
            // for this job.  cache the socket status on root scope
            $rootScope['lastSocketStatus' + data.job_id] = data.status;
        }
    }));

    if (statusSocket && statusSocket[1]) {
        statusSocket[1]();
    }

    $scope.$on('$destroy', function(){
        if (statusSocket && statusSocket[1]) {
            statusSocket[1]();
        }
        $( ".JobResultsStdOut-aLineOfStdOut" ).remove();
        cancelRequests = true;
        eventQueue.initialize();
        Object.keys($scope.events)
            .forEach(v => {
                $scope.events[v].$destroy();
                $scope.events[v] = null;
            });
        $scope.events = {};
        timerService.destroyTimer(runTimeElapsedTimer);
        if (bufferInterval) {
            clearInterval(bufferInterval);
        }
        toDestroy.forEach(closureFunc => closureFunc());
    });
  }
})();
