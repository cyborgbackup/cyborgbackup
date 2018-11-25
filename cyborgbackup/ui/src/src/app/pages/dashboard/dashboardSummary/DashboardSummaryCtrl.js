(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.dashboard')
      .controller('DashboardSummaryCtrl', DashboardSummaryCtrl);

  /** @ngInject */
  function DashboardSummaryCtrl($scope, $timeout, baConfig, GetBasePath, QuerySet, baUtil) {
    var getValue = function(item, params, id=false){
      QuerySet.search(GetBasePath(item)+params).then(function(data){
        _.forEach($scope.charts, function(chart){
          if((id && chart.object == id) || chart.object == item){
             chart.stats = data.data.count;
           }
        })
      });
    };

    $scope.charts = [{
      description: 'Clients',
      object: 'clients',
      stats: getValue('clients', ''),
      icon: 'tasks',
    }, {
      description: 'Backups',
      object: 'backups',
      stats: getValue('jobs', '', 'backups'),
      icon: 'compressed',
    }, {
      description: 'Policies',
      object: 'policies',
      stats: getValue('policies', ''),
      icon: 'file',
    }, {
      description: 'Errors',
      object: 'errors',
      stats: getValue('jobs', '?or__status=failed&or__status=error', 'errors'),
      icon: 'exclamation-sign',
    }];
  }
})();
