# Primary sources and differentiation

Research checked 2026-10-05. No user, university or customer data used.

- QGIS auxiliary storage: label data-defined overrides can be stored in auxiliary fields joined through a primary key. Export includes the original geometry. https://docs.qgis.org/4.2/en/docs/user_manual/working_with_vector/vector_properties.html#auxiliary-storage-properties
- QGIS official install guidance: https://qgis.org/resources/installation-guide/
- QGIS label settings and data-defined properties: https://api.qgis.org/api/3.40/classQgsPalLayerSettings.html
- QGIS property XML is keyed by property names: https://api.qgis.org/api/3.34/qgspropertycollection_8cpp_source.html
- QGIS text-format serialization: https://api.qgis.org/api/3.34/qgstextformat_8cpp_source.html
- Native render evidence API: https://www.qgis.org/pyqgis/master/core/QgsMapRendererJob.html and https://www.qgis.org/pyqgis/master/core/QgsLabelingResults.html
- AttributeTransfer uses geometry/proximity: https://plugins.qgis.org/plugins/AttributeTransfer/
- Project Packager packages project dependencies: https://plugins.qgis.org/plugins/ProjectPackager/

The proposed difference is explicit stable-key reconciliation with a deliberate movement policy per moved pinned label and a portable field-bound result. This is a workflow inference; QGIS's native joins/field calculator can be used manually for related work. Product novelty and willingness to pay have not been established.
