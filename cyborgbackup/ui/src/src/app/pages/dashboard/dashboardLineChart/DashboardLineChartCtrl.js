(function () {
  'use strict';

  angular.module('CyBorgBackup.pages.dashboard')
      .controller('DashboardLineChartCtrl', DashboardLineChartCtrl);

  /** @ngInject */
  function DashboardLineChartCtrl(baConfig, QuerySet, GetBasePath, layoutPaths, baUtil) {
    var layoutColors = baConfig.colors;
    var graphColor = baConfig.theme.blur ? '#000000' : layoutColors.primary;

    QuerySet.search(GetBasePath('stats')).then(function(data){

      var chart = AmCharts.makeChart('amchart', {
        type: 'serial',
        theme: 'blur',
        marginTop: 15,
        marginRight: 15,
        dataProvider: data.data,
        categoryField: 'date',
        categoryAxis: {
          parseDates: true,
          gridAlpha: 0,
          color: layoutColors.defaultText,
          axisColor: layoutColors.defaultText
        },
        valueAxes: [
          {
            id: "sizeAxis",
            position: "left",
            minVerticalGap: 50,
            gridAlpha: 0,
            color: layoutColors.defaultText,
            axisColor: layoutColors.defaultText
          },{
            id: "stateAxis",
            position: "right",
            stackType: "regular",
            minVerticalGap: 50,
            gridAlpha: 0,
            color: layoutColors.defaultText,
            axisColor: layoutColors.defaultText
          }
        ],
        graphs: [
          {
            id: 'g0',
            bullet: 'none',
            useLineColorForBulletBorder: true,
            lineColor: baUtil.hexToRGB(graphColor, 0.3),
            lineThickness: 1,
            negativeLineColor: layoutColors.danger,
            type: 'smoothedLine',
            valueField: 'size',
            valueAxis: 'sizeAxis',
            balloonText: "original [[value]] bytes",
            fillAlphas: 1,
            fillColorsField: 'lineColor'
          },
          {
            id: 'g1',
            bullet: 'none',
            useLineColorForBulletBorder: true,
            lineColor: baUtil.hexToRGB(graphColor, 0.3),
            lineThickness: 1,
            negativeLineColor: layoutColors.danger,
            type: 'smoothedLine',
            valueField: 'dedup',
            valueAxis: 'sizeAxis',
            balloonText: "dedup [[value]] bytes",
            fillAlphas: 1,
            fillColorsField: 'lineColor'
          },
          {
            id: 'g2',
            bullet: 'none',
            useLineColorForBulletBorder: true,
            lineColor: baUtil.hexToRGB(layoutColors.success, 0.5),
            lineThickness: 1,
            negativeLineColor: layoutColors.danger,
            type: 'column',
            valueField: 'success',
            valueAxis: 'stateAxis',
            balloonText: "success [[value]]",
            fillAlphas: 1,
            fillColorsField: 'lineColor'
          },
          {
            id: 'g3',
            bullet: 'none',
            useLineColorForBulletBorder: true,
            lineColor: baUtil.hexToRGB(layoutColors.warning, 0.5),
            lineThickness: 1,
            negativeLineColor: layoutColors.danger,
            type: 'column',
            valueField: 'failed',
            valueAxis: 'stateAxis',
            balloonText: "failed [[value]]",
            fillAlphas: 1,
            fillColorsField: 'lineColor'
          }
        ],
        chartCursor: {
          categoryBalloonDateFormat: 'YYYY-MM-DD',
          categoryBalloonColor: '#4285F4',
          categoryBalloonAlpha: 0.7,
          cursorAlpha: 0,
          valueLineEnabled: true,
          valueLineBalloonEnabled: true,
          valueLineAlpha: 0.5
        },
        dataDateFormat: 'YYYY-MM-DD',
        export: {
          enabled: true
        },
        creditsPosition: 'bottom-right',
        zoomOutButton: {
          backgroundColor: '#fff',
          backgroundAlpha: 0
        },
        zoomOutText: '',
        pathToImages: layoutPaths.images.amChart
      });
    });
  }
})();
