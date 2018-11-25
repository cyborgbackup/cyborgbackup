(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.job')
      .service('parseStdout', parseStdout);


      /** @ngInject */
      function parseStdout($log){
            var val = {
                // parses stdout string from api and formats various codes to the
                // correct dom structure
                prettify: function(line, unstyled){
                    line = line
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/"/g, "&quot;")
                        .replace(/'/g, "&#039;");

                    // TODO: remove once Chris's fixes to the [K lines comes in
                    if (line.indexOf("[K") > -1) {
                        $log.error(line);
                    }

                    if(!unstyled){
                        // add span tags with color styling
                        line = line.replace(/u001b/g, '');

                        // ansi classes
                        /* jshint ignore:start */
                        line = line.replace(/()\[1;im/g, '<span class="JobResultsStdOut-cappedLine">');
                        line = line.replace(/()\[0;30m/g, '<span class="ansi30">');
                        line = line.replace(/()\[1;30m/g, '<span class="ansi1 ansi30">');
                        line = line.replace(/()\[[0,1];31m/g, '<span class="ansi1 ansi31">');
                        line = line.replace(/()\[0;32m(=|)/g, '<span class="ansi32">');
                        line = line.replace(/()\[0;32m1/g, '<span class="ansi36">');
                        line = line.replace(/()\[0;33m/g, '<span class="ansi33">');
                        line = line.replace(/()\[0;34m/g, '<span class="ansi34">');
                        line = line.replace(/()\[[0,1];35m/g, '<span class="ansi35">');
                        line = line.replace(/()\[0;36m/g, '<span class="ansi36">');
                        line = line.replace(/(<host.*?>)\s/g, '$1');

                        //end span
                        line = line.replace(/()\[0m/g, '</span>');
                        /* jshint ignore:end */
                    } else {
                        // For the host event modal in the standard out tab,
                        // the styling isn't necessary
                        line = line.replace(/u001b/g, '');

                        // ansi classes
                        /* jshint ignore:start */
                        line = line.replace(/()\[[0,1];3[0-9]m(1|=|)/g, '');
                        line = line.replace(/(<host.*?>)\s/g, '$1');

                        //end span
                        line = line.replace(/()\[0m/g, '');
                        /* jshint ignore:end */
                    }

                    return line;
                },
                // adds anchor tags and tooltips to host status lines
                getAnchorTags: function(event){
                    if(event.event_name.indexOf("runner_") === -1){
                        return `"`;
                    }
                    else{
                        return ` JobResultsStdOut-stdoutColumn--clickable" ui-sref="jobResult.host-event.json({eventId: ${event.id}, taskUuid: '${event.event_data.task_uuid}' })" data-placement="top"`;
                    }

                },
                // this adds classes based on event data to the
                // .JobResultsStdOut-aLineOfStdOut element
                getLineClasses: function(event, line, lineNum) {
                    var string = "";

                    if (lineNum === event.end_line) {
                        // used to tell you where to put stuff in the pane
                        string += ` next_is_${event.end_line + 1}`;
                    }

                    string += " not_skeleton";

                    // TODO: adding this line_num_XX class is hacky because the
                    // line number is availabe in children of this dom element
                    string += " line_num_" + lineNum;

                    return string;
                },
                getStartTimeBadge: function(event, line){
                    // This will return a div with the badge class
                    // for the start time to show at the right hand
                    // side of each stdout header line.
                    // returns an empty string if not a header line
                    var emptySpan = "", time;
                    if ((event.event_name === "playbook_on_play_start" ||
                        event.event_name === "playbook_on_task_start") &&
                        line !== "") {
                            //time =  moment(event.created).format('HH:mm:ss');
                            return `<div class="badge JobResults-timeBadge ng-binding">${event.created}</div>`;
                    }
                    else if(event.event_name === "playbook_on_stats" && line.indexOf("PLAY") > -1){
                        //time =  moment(event.created).format('HH:mm:ss');
                        return `<div class="badge JobResults-timeBadge ng-binding">${event.created}</div>`;
                    }
                    else {
                        return emptySpan;
                    }

                },
                // used to add expand/collapse icon next to line numbers of headers
                getCollapseIcon: function(event, line) {
                    var clickClass,
                        expanderizerSpecifier;

                    var emptySpan = `
        <span class="JobResultsStdOut-lineExpander"></span>`;

                    if ((event.event_name === "playbook_on_play_start" ||
                        event.event_name === "playbook_on_task_start") &&
                        line !== "") {
                            if (event.event_name === "playbook_on_play_start" &&
                                line.indexOf("PLAY") > -1) {
                                    // play header specific attrs
                                    expanderizerSpecifier = "play";
                                    clickClass = "play_" +
                                        event.event_data.play_uuid;
                            } else if (line.indexOf("TASK") > -1 ||
                                line.indexOf("RUNNING HANDLER") > -1) {
                                    // task header specific attrs
                                    expanderizerSpecifier = "task";
                                    clickClass = "task_" +
                                        event.event_data.task_uuid;
                            } else {
                                // header lines that don't have PLAY, TASK,
                                // or RUNNING HANDLER in them don't get
                                // expand icon.
                                // This provides cowsay support.
                                return emptySpan;
                            }


                        var expandDom = `
        <span class="JobResultsStdOut-lineExpander">
            <i class="JobResultsStdOut-lineExpanderIcon fa fa-caret-down expanderizer
                expanderizer--${expanderizerSpecifier} expanded"
                ng-click="toggleLine($event, '.${clickClass}')"
                data-uuid="${clickClass}">
            </i>
        </span>`;
                        return expandDom;
                    } else {
                        // non-header lines don't get an expander
                        return emptySpan;
                    }
                },
                distributeColors: function(lines) {
                    var colorCode;
                    return lines.map(line => {

                        if (colorCode) {
                            line = colorCode + line;
                        }

                        if (line.indexOf("[0m") === -1) {
                            if (line.indexOf("[1;31m") > -1) {
                                colorCode = "[1;31m";
                            } else if (line.indexOf("[1;30m") > -1) {
                                colorCode = "[1;30m";
                            } else if (line.indexOf("[0;31m") > -1) {
                                colorCode = "[0;31m";
                            } else if (line.indexOf("[0;32m=") > -1) {
                                colorCode = "[0;32m=";
                            } else if (line.indexOf("[0;32m1") > -1) {
                                colorCode = "[0;32m1";
                            } else if (line.indexOf("[0;32m") > -1) {
                                colorCode = "[0;32m";
                            } else if (line.indexOf("[0;33m") > -1) {
                                colorCode = "[0;33m";
                            } else if (line.indexOf("[0;34m") > -1) {
                                colorCode = "[0;34m";
                            } else if (line.indexOf("[0;35m") > -1) {
                                colorCode = "[0;35m";
                            }  else if (line.indexOf("[1;35m") > -1) {
                                colorCode = "[1;35m";
                            } else if (line.indexOf("[0;36m") > -1) {
                                colorCode = "[0;36m";
                            }
                        } else {
                            colorCode = null;
                        }

                        return line;
                    });
                },
                getLineArr: function(event) {
                    let lineNums = _.range(event.start_line + 1,
                        event.end_line + 1);

                    // hack around no-carriage return issues
                    if (!lineNums.length) {
                        lineNums = [event.start_line + 1];
                    }

                    let lines = event.stdout
                        .replace("\t", "        ")
                        .split("\r\n");

                    if (lineNums.length > lines.length) {
                        lineNums = lineNums.slice(0, lines.length);
                    }

                    lines = this.distributeColors(lines);

                    // hack around no-carriage return issues
                    if (lineNums.length === lines.length) {
                        return _.zip(lineNums, lines);
                    }

                    return _.zip(lineNums, lines).slice(0, -1);
                },
                actualEndLine: function(event) {
                    return event.start_line + this.getLineArr(event).length;
                },
                // public function that provides the parsed stdout line, given a
                // job_event
                parseStdout: function(event){
                    // this utilizes the start/end lines and stdout blob
                    // to create an array in the format:
                    // [
                    //     [lineNum, lineText],
                    //     [lineNum, lineText],
                    // ]
                    var lineArr = this.getLineArr(event);

                    // this takes each `[lineNum: lineText]` element and calls the
                    // relevant helper functions in this service to build the
                    // parsed line of standard out
                    lineArr = lineArr
                        .map(lineArr => {
                            return `
        <div class="JobResultsStdOut-aLineOfStdOut${this.getLineClasses(event, lineArr[1], lineArr[0])}">
            <div class="JobResultsStdOut-lineNumberColumn">${this.getCollapseIcon(event, lineArr[1])}${lineArr[0]}</div>
            <div class="JobResultsStdOut-stdoutColumn${this.getAnchorTags(event)}><span ng-non-bindable>${this.prettify(lineArr[1])}</span>${this.getStartTimeBadge(event, lineArr[1])}</div>
        </div>`;
                        });

                    // this joins all the lines for this job_event together and
                    // returns to the mungeEvent function
                    return lineArr.join("");
                }
            };
            return val;
        }

})();
