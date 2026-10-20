/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

const THREE_CDN = "https://cdn.jsdelivr.net/npm/three@0.134.0/build/three.min.js";
const STL_LOADER_CDN = "https://cdn.jsdelivr.net/npm/three@0.134.0/examples/js/loaders/STLLoader.js";
const ORBIT_CDN = "https://cdn.jsdelivr.net/npm/three@0.134.0/examples/js/controls/OrbitControls.js";

class Model3DViewer extends Component {
    static template = "jewelry_3d_library.Model3DViewer";
    static props = ["action", "actionStack"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.canvasRef = useRef("canvas");
        this.state = useState({ loading: true, error: null, modelName: "" });
        this.animFrameId = null;
        this.renderer = null;

        onMounted(async () => {
            const resId = this.props.action.params.res_id;
            await this._initViewer(resId);
        });

        onWillUnmount(() => {
            if (this.animFrameId) {
                cancelAnimationFrame(this.animFrameId);
            }
            if (this.renderer) {
                this.renderer.dispose();
            }
        });
    }

    async _initViewer(resId) {
        try {
            const [record] = await this.orm.read(
                "jewelry.model.3d",
                [resId],
                ["name", "stl_file"]
            );
            this.state.modelName = record.name;

            if (!record.stl_file) {
                this.state.error = "No STL file found for this model.";
                this.state.loading = false;
                return;
            }

            await loadJS(THREE_CDN);
            await loadJS(STL_LOADER_CDN);
            await loadJS(ORBIT_CDN);

            const THREE = window.THREE;
            const canvas = this.canvasRef.el;
            const w = canvas.clientWidth;
            const h = canvas.clientHeight;

            this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
            this.renderer.setSize(w, h, false);
            this.renderer.setPixelRatio(window.devicePixelRatio);

            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0xf2ede6);

            const camera = new THREE.PerspectiveCamera(45, w / h, 0.01, 100000);

            // Lights
            scene.add(new THREE.AmbientLight(0xffffff, 0.5));
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
            dirLight.position.set(5, 10, 7);
            scene.add(dirLight);
            const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
            dirLight2.position.set(-5, -3, -5);
            scene.add(dirLight2);

            // Parse STL from base64
            const binary = atob(record.stl_file);
            const buf = new ArrayBuffer(binary.length);
            const bytes = new Uint8Array(buf);
            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }

            const loader = new THREE.STLLoader();
            const geometry = loader.parse(buf);
            geometry.computeVertexNormals();
            geometry.center();

            const material = new THREE.MeshPhongMaterial({
                color: 0xd4a843,
                specular: 0x553300,
                shininess: 60,
            });
            const mesh = new THREE.Mesh(geometry, material);
            scene.add(mesh);

            // Fit camera
            const box = new THREE.Box3().setFromObject(mesh);
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            camera.position.set(0, maxDim * 0.5, maxDim * 2.5);
            camera.lookAt(0, 0, 0);

            // Grid
            const grid = new THREE.GridHelper(maxDim * 3, 20, 0xccbbaa, 0xddccbb);
            grid.position.y = box.min.y;
            scene.add(grid);

            // Controls
            const controls = new THREE.OrbitControls(camera, this.renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.08;
            controls.minDistance = maxDim * 0.5;
            controls.maxDistance = maxDim * 10;

            this.state.loading = false;

            const animate = () => {
                this.animFrameId = requestAnimationFrame(animate);
                controls.update();
                this.renderer.render(scene, camera);
            };
            animate();

        } catch (e) {
            this.state.error = e.message || "Failed to load 3D model.";
            this.state.loading = false;
        }
    }

    goBack() {
        this.actionService.restore();
    }
}

registry.category("actions").add("jewelry_3d_viewer", Model3DViewer);
