/** @odoo-module **/

function openOrderImage(orderId) {
    if (!orderId) {
        return;
    }
    const url = `/web/image?model=jewelry.repair.order&id=${orderId}&field=item_image`;
    window.open(url, "_blank", "noopener,noreferrer");
}

document.addEventListener("click", (event) => {
    const kanbanImage = event.target.closest("[data-jr-order-image-id]");
    if (kanbanImage) {
        event.preventDefault();
        event.stopPropagation();
        openOrderImage(kanbanImage.dataset.jrOrderImageId);
    }
});
