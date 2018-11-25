(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.dashboard')
      .controller('DashboardCalendarCtrl', DashboardCalendarCtrl);

  /** @ngInject */
  function DashboardCalendarCtrl($scope, baConfig, QuerySet, GetBasePath) {
    var dashboardColors = baConfig.colors.dashboard;
    $scope.element = $('#calendar').fullCalendar({
      //height: 335,
      header: {
        left: 'today',
        center: 'title',
        right: 'month,agendaWeek,agendaDay'
      },
      //defaultDate: '2016-03-08',
      selectable: true,
      selectHelper: true,
      select: function (start, end) {
        var title = prompt('Event Title:');
        var eventData;
        if (title) {
          eventData = {
            title: title,
            start: start,
            end: end
          };
          $element.fullCalendar('renderEvent', eventData, true); // stick? = true
        }
        $element.fullCalendar('unselect');
      },
      editable: true,
      eventLimit: true, // allow "more" link when too many events
      events: []
    });
    QuerySet.search(GetBasePath('policies')).then(function(data){
      var results = data.data.results;
      _.forEach(results, function(value, key){
        QuerySet.search(value.related['calendar']).then(function(calendarData){
          _.forEach(calendarData.data, function(start){
            $scope.element.fullCalendar('renderEvent', {title: value.name, start: start});
          });
        });
      });
    });
  }
})();
