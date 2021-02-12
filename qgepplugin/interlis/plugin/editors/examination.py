from sqlalchemy.orm import aliased

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QListWidgetItem

from qgis.utils import iface
from qgis.core import QgsProject, QgsFeature

from ...qgep.model_qgep import get_qgep_model
from .base import Editor


class ExaminationEditor(Editor):

    class_name = 'examination'

    def init_widget(self):
        self.reach_layer = QgsProject.instance().mapLayersByName("vw_qgep_reach")[0]
        self.widget.selectorWidget.set_layer(self.reach_layer)
        self.widget.selectorWidget.set_canvas(iface.mapCanvas())
        # self.widget.assignButton.pressed.connect(self.assign_button_clicked)  # doesn't work ?!
        self.widget.assignButton.pressed.connect(lambda: self.assign_button_clicked())
        self.widget.unassignButton.pressed.connect(lambda: self.unassign_button_clicked())
        self.widget.suggestedListWidget.currentItemChanged.connect(self.suggested_reach_changed)
        self.update_widget()

    def update_widget(self):
        # 1. Populate suggested channels
        self.widget.suggestedListWidget.clear()
        for channel in self.get_suggested_structures():
            widget_item = QListWidgetItem(f"Channel {channel.obj_id}/{channel.identifier}")
            widget_item.setData(Qt.UserRole, channel.obj_id)
            self.widget.suggestedListWidget.addItem(widget_item)
        for channel in self.get_suggested_structures(inverted=True):
            widget_item = QListWidgetItem(f"Channel {channel.obj_id}/{channel.identifier} [inverted]")
            widget_item.setData(Qt.UserRole, channel.obj_id)
            self.widget.suggestedListWidget.addItem(widget_item)

        # 2. Populated assigned structures
        self.widget.assignedWidget.clear()
        for structure in self.get_assigned_structures():
            widget_item = QListWidgetItem(f"Structure {structure.obj_id}/{structure.identifier}")
            widget_item.setData(Qt.UserRole, structure.obj_id)
            self.widget.assignedWidget.addItem(widget_item)

    def suggested_reach_changed(self, current_item, _previous_item):
        obj_id = current_item.data(Qt.UserRole)
        features = self.reach_layer.getFeatures(f"ws_obj_id = '{obj_id}'")
        try:
            feature = next(features)
        except StopIteration:
            # Not found
            return
        self.widget.selectorWidget.set_feature(feature)

    def assign_button_clicked(self):

        QGEP = get_qgep_model()

        feature: QgsFeature = self.widget.selectorWidget.feature
        exam_to_wastewater_structure = QGEP.re_maintenance_event_wastewater_structure(
            fk_wastewater_structure=feature["ws_obj_id"],
            fk_maintenance_event=self.obj.obj_id,
        )
        self.session.add(exam_to_wastewater_structure)
        self.session.flush()

        self.validate()
        self.main_dialog.refresh_editor(self)
        self.main_dialog.update_tree()

    def unassign_button_clicked(self):
        QGEP = get_qgep_model()

        structure_id = self.widget.assignedWidget.currentItem().data(Qt.UserRole)
        self.session.query(QGEP.re_maintenance_event_wastewater_structure) \
            .filter(QGEP.re_maintenance_event_wastewater_structure.fk_maintenance_event == self.obj.obj_id) \
            .filter(QGEP.re_maintenance_event_wastewater_structure.fk_wastewater_structure == structure_id) \
            .delete()
        self.session.flush()

        self.validate()
        self.main_dialog.refresh_editor(self)
        self.main_dialog.update_tree()

    def validate(self):
        count = self.get_assigned_structures().count()
        if count == 0:
            self.validity = Editor.WARNING
            self.message = 'Not associated any wastewater structures.'
        elif count == 1:
            self.validity = Editor.VALID
            self.message = 'Assigned'
        else:
            self.validity = Editor.WARNING
            self.message = f'Associated to more than one ({count}) wastewater structures. This is allowed by the datamodel, but discouraged.'

    def get_suggested_structures(self, inverted=False):

        QGEP = get_qgep_model()

        if not inverted:
            from_id = self.obj.from_point_identifier
            to_id = self.obj.to_point_identifier
        else:
            from_id = self.obj.to_point_identifier
            to_id = self.obj.from_point_identifier

        wastewater_ne_from = aliased(QGEP.wastewater_networkelement)
        wastewater_ne_to = aliased(QGEP.wastewater_networkelement)
        rp_from = aliased(QGEP.reach_point)
        rp_to = aliased(QGEP.reach_point)

        return self.session.query(QGEP.wastewater_structure) \
            .join(QGEP.reach) \
            .join(rp_from, rp_from.obj_id == QGEP.reach.fk_reach_point_from) \
            .join(wastewater_ne_from, wastewater_ne_from.obj_id == rp_from.fk_wastewater_networkelement) \
            .join(rp_to, rp_to.obj_id == QGEP.reach.fk_reach_point_to) \
            .join(wastewater_ne_to, wastewater_ne_to.obj_id == rp_to.fk_wastewater_networkelement) \
            .filter(wastewater_ne_from.identifier == from_id, wastewater_ne_to.identifier == to_id)

    def get_assigned_structures(self):
        QGEP = get_qgep_model()
        return self.session.query(QGEP.wastewater_structure) \
            .join(QGEP.re_maintenance_event_wastewater_structure) \
            .filter(QGEP.re_maintenance_event_wastewater_structure.fk_maintenance_event == self.obj.obj_id)
