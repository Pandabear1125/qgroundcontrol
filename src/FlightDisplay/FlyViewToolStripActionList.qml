/****************************************************************************
 *
 * (c) 2009-2020 QGROUNDCONTROL PROJECT <http://www.qgroundcontrol.org>
 *
 * QGroundControl is licensed according to the terms in the file
 * COPYING.md in the root of the source code directory.
 *
 ****************************************************************************/

import QtQml.Models 2.12

import QGroundControl           1.0
import QGroundControl.Controls  1.0

ToolStripActionList {
    id: _root

    signal displayPreFlightChecklist

    model: [
        ToolStripAction {
            text:           qsTr("Plan")
            iconSource:     "/qmlimages/Plan.svg"
            onTriggered:    mainWindow.showPlanView()
        },

		ToolStripAction {
			text: qsTr("Console")
			iconSource: "/qmlimages/MavlinkConsoleIcon"

			onTriggered: {
				mainWindow.createrWindowedAnalyzePage(
					qsTr("MAVLink Console"),
					"qrc:/qml/MavlinkConsolePage.qml"
				)

				mainWindow.showFlyView()
			}
		},

		ToolStripAction {
			text: qsTr("Logs")
			iconSource: "/qmlimages/LogDownloadIcon"

			onTriggered: {
				mainWindow.createrWindowedAnalyzePage(
					qsTr("Log Download"),
					"qrc:/qml/LogDownloadPage.qml"
				)

				mainWindow.showFlyView()
			}
		},

		ToolStripAction {
			text: qsTr("Parameters")
			iconSource: "/qmlimages/Gears.svg"

			onTriggered: mainWindow.showParametersTool()
		},

        PreFlightCheckListShowAction { onTriggered: displayPreFlightChecklist() },
        GuidedActionTakeoff { },
        GuidedActionLand { },
        GuidedActionRTL { },
        GuidedActionPause { },
        GuidedActionActionList { },
        GuidedActionGripper { }
    ]
}
