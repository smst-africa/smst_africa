import {
  showErrorMessage,
  showSuccessMessage,
} from '/static/js/common/notification.prod.js';
import {
  saveImage,
  fadeOutModal,
  parseImage,
  storeNotifications,
  getStoredNotifications,
  renderNotifications,
} from '/static/js/common/functions.prod.js';

document.addEventListener('DOMContentLoaded', function () {
  let access = localStorage.getItem('access') || null;
  let smstProductMap = {};
  $('.profileHolder').on('click', function () {
    let $helper = $('.helperHolder');
    if ($helper.hasClass('animate__fadeInDown')) {
      $helper.removeClass('animate__fadeInDown').addClass('animate__fadeOutUp');
    } else {
      $.ajax({
        type: 'GET',
        url: 'https://cloud.smartstock.africa/smst_user/',
        headers: {
          Authorization: `Bearer ${access}`,
        },
        success: function (response) {
          Object.entries(response).forEach(([key, value]) => {
            if (key == 'username') {
              $('.profilePhotoHolder')
                .empty()
                .append(`<span>${value.charAt(0)}</span>`);
            }
            $(`#${key}`).empty().append(value);
          });

          $('.helperHolder')
            .removeClass('animate__fadeOutUp')
            .addClass('animate__fadeInDown');
        },
      });
    }
  });

  $('body').on('click', '.addImageHolder', function () {
    $('#imageInput').trigger('click');
  });

  $('body').on('change', '#imageInput', function (e) {
    parseImage(e);
  });

  $('body').on('pointerdown', '#descriptionButton', function (e) {
    e.preventDefault();
  });

  $('body').on('click', '#descriptionButton', function () {
    const $pdi = $('#productDescriptionInput');
    let descriptions = $pdi.val().trim();
    let productDescriptionInputValue = new Array();
    if (descriptions.length) {
      productDescriptionInputValue = JSON.parse(descriptions);
      if (productDescriptionInputValue.length >= 5) {
        showErrorMessage(
          gettext('Maximum Descriptions'),
          gettext('You have reached your free limit for descriptions.')
        );
        return;
      }
    }
    let $descriptionInputs = $('.doubleInputHolder').find('textarea');
    let emptyField = false;
    $descriptionInputs.each(function () {
      let value = $(this).val().trim();

      if (!value.length) {
        emptyField = true;
        showErrorMessage(
          gettext('Fill Empty Fields'),
          gettext('Kindly fill in the empty fields.')
        );
        $(this).focus();
        return false; // Break the loop
      }
      emptyField = false;
    });
    const descriptionData = {
      descriptionType: $('#descriptionType').val().trim(),
      descriptionValue: $('#descriptionValue').val().trim(),
    };
    if (emptyField) {
      return;
    }

    let $prodDesc = $(
      '<div class="productDescription flex animate__animated animate__fadeInUp"></div>'
    );
    let $descHolder = $('<div class="prodDesc"></div>');
    let $descType = $('<div class="descriptionType"></div>').append(
      descriptionData.descriptionType
    );
    let $descValue = $('<div class="descriptionValue"></div>').append(
      descriptionData.descriptionValue
    );

    let $descriptionOptions = $(
      `
        <div class="decriptionOptions flex align-center">
          <div class="editDescriptionButton descriptionOptionButton">
            <svg width="24px" height="24px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M15.4998 5.49994L18.3282 8.32837M3 20.9997L3.04745 20.6675C3.21536 19.4922 3.29932 18.9045 3.49029 18.3558C3.65975 17.8689 3.89124 17.4059 4.17906 16.9783C4.50341 16.4963 4.92319 16.0765 5.76274 15.237L17.4107 3.58896C18.1918 2.80791 19.4581 2.80791 20.2392 3.58896C21.0202 4.37001 21.0202 5.63634 20.2392 6.41739L8.37744 18.2791C7.61579 19.0408 7.23497 19.4216 6.8012 19.7244C6.41618 19.9932 6.00093 20.2159 5.56398 20.3879C5.07171 20.5817 4.54375 20.6882 3.48793 20.9012L3 20.9997Z" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="deleteDescriptionButton descriptionOptionButton">
            <svg width="24px" height="24px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M10 12V17" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 12V17" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M4 7H20" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6 10V18C6 19.6569 7.34315 21 9 21H15C16.6569 21 18 19.6569 18 18V10" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M9 5C9 3.89543 9.89543 3 11 3H13C14.1046 3 15 3.89543 15 5V7H9V5Z" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </div>
      `
    );

    $('.productDescriptions').append(
      $prodDesc.append(
        $descHolder.append($descType, $descValue),
        $descriptionOptions
      )
    );

    productDescriptionInputValue.push(descriptionData);
    $pdi.val(JSON.stringify(productDescriptionInputValue));

    if (productDescriptionInputValue.length >= 5) {
      $('.doubleInputHolder').find('button').prop('disabled', true);
      showErrorMessage(
        gettext('Maximum Descriptions Reached'),
        gettext('You have reached your maximum of 5 descriptions.')
      );
    }
    $descriptionInputs.text('');
  });

  $('body').on('click', '#cancelEditing', function () {
    fadeOutModal('.imageEdit', '.imageEditHolder');
  });

  $('body').on('click', '#saveEditing', function () {
    saveImage();
  });

  $('body').on('click', '.descriptionOptionButton', function () {
    let $parent = $(this).closest('.productDescription');
    let index = $parent.index();
    let descriptionData = JSON.parse(
      $('#productDescriptionInput').val().trim()
    );
    if ($(this).hasClass('editDescriptionButton')) {
      let description = descriptionData[index];
      $('#descriptionType').text(description.descriptionType);
      $('#descriptionValue').text(description.descriptionValue);
    }

    descriptionData.splice(index, 1);
    $('#productDescriptionInput').val(JSON.stringify(descriptionData));
    $parent.remove();
    if ($(this).hasClass('deleteDescriptionButton')) {
      showErrorMessage(
        gettext('Deleted Description'),
        gettext('You have removed the description')
      );
    }
    $('#descriptionButton').prop('disabled', false);
  });

  $('body').on('click', '#createProductButton', function () {
    $(this).prop('disabled', true);
    let imageFile = $('#imageInput')[0].files[0];
    let productName = $('#productName').val().trim();
    let productDescription = $('#productDescriptionInput').val().trim();
    let formData = new FormData();
    formData.append('product_image', imageFile);
    formData.append('product_name', productName);
    formData.append('product_description', productDescription);
    $.ajax({
      method: 'POST',
      url: 'https://cloud.smartstock.africa/stock_products/',
      headers: {
        Authorization: `Bearer ${access}`,
      },
      processData: false,
      contentType: false,
      data: formData,
      success: function () {
        showSuccessMessage(
          gettext('Processing'),
          gettext('Your request is being processed')
        );
      },
    });
  });

  $('body').on('click', '.messageIconHolder', function () {
    if ($('.app_notification_grand_parent').length) {
      $('.app_notification_grand_parent')
        .removeClass('animate__fadeInTopRight')
        .addClass('animate__fadeOutTopRight')
        .one('animationend', function () {
          $(this).remove();
        });
    } else {
      const storedNotifications = getStoredNotifications();
      if (storedNotifications.length) {
        renderNotifications(storedNotifications);
      } else {
        $.ajax({
          type: 'GET',
          url: 'https://cloud.smartstock.africa/notifications/',
          headers: {
            Authorization: `Bearer ${access}`,
          },
          success: function (response) {
            storeNotifications(response.results);
            renderNotifications(response.results);
          },
        });
      }
    }
  });

  $('body').on('click', '.app_notification', function () {
    $(this).removeClass('unread');
    let notificationId = $(this).data('notification-id').trim();
    let storedNotifications = getStoredNotifications();
    storeNotifications(
      storedNotifications.map((notification) =>
        notification.notificationId == notificationId
          ? { ...notification, notificationRead: true }
          : notification
      )
    );
    $.ajax({
      type: 'POST',
      url: `https://cloud.smartstock.africa/notifications/${notificationId}/read_notification/`,
      headers: {
        Authorization: `Bearer ${access}`,
      },
      success: function (response) {
        console.log(response);
      },
    });
  });

  /* ---------- Smst Stocks Modal ---------- */
  const smstTransactionApi = 'https://cloud.smartstock.africa/stock_products/';
  const smstProductApiBase = 'https://cloud.smartstock.africa/stock_products/';

  const escSmst = (t) =>
    String(t == null ? '' : t)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

  function closeSmstStocksModal() {
    $('#smst_stocks_modal').remove();
  }

  function openSmstStocksModal(product) {
    closeSmstStocksModal();
    const productImage = escSmst(product.product_image || '');
    const productName = escSmst(product.product_name);
    const productId = escSmst(product.id);

    const $modal = $(`
      <div id="smst_stocks_modal" class="smst_stocks_modal" aria-modal="true" role="dialog">
        <div class="smst_stocks_modal_backdrop"></div>
        <div class="smst_stocks_modal_card animate__animated animate__fadeInUp">
          <button type="button" class="smst_stocks_modal_close" aria-label="${gettext('Close')}"><span>×</span></button>
          <div class="smst_stocks_modal_header">
            <div class="smst_stocks_modal_image">
              <img src="${productImage}" alt="${productName}" loading="lazy">
            </div>
            <div class="smst_stocks_modal_meta">
              <div class="smst_stocks_modal_sku">#${productId}</div>
              <h2 class="smst_stocks_modal_title">${productName}</h2>
              <p class="smst_stocks_modal_subtitle">${gettext('Stock Item')}</p>
            </div>
          </div>
          <div class="smst_stocks_modal_tabs">
            <button type="button" class="smst_stocks_modal_tab smst_stocks_modal_tab_active" data-tab="information">${gettext('Information')}</button>
            <button type="button" class="smst_stocks_modal_tab" data-tab="transactions">${gettext('Transactions')}</button>
          </div>
          <div class="smst_stocks_modal_panels">
            <div class="smst_stocks_modal_panel smst_stocks_modal_panel_active" id="smst_stocks_panel_information">
              
              <div class="smst_stocks_modal_actions">
                <button type="button" class="smst_stocks_modal_btn smst_stocks_modal_btn_edit" data-action="edit"><span>${gettext('Edit Product')}</span></button>
                <button type="button" class="smst_stocks_modal_btn smst_stocks_modal_btn_delete" data-action="delete"><span>${gettext('Delete Product')}</span></button>
                <button type="button" class="smst_stocks_modal_btn smst_stocks_modal_btn_buy" data-action="buy"><span>${gettext('Buy Product')}</span></button>
                <button type="button" class="smst_stocks_modal_btn smst_stocks_modal_btn_sell" data-action="sell"><span>${gettext('Sell Product')}</span></button>
              </div>
            </div>
            <div class="smst_stocks_modal_panel" id="smst_stocks_panel_transactions">
              <div class="smst_stocks_modal_section_title">${gettext('Product Transactions')}</div>
              <table class="smst_stocks_transactions_table">
                <thead>
                  <tr>
                    <th class="smst_stocks_tx_cell">${gettext('Date')}</th>
                    <th class="smst_stocks_tx_cell">${gettext('Type')}</th>
                    <th class="smst_stocks_tx_cell">${gettext('Quantity')}</th>
                    <th class="smst_stocks_tx_cell">${gettext('Reference')}</th>
                    <th class="smst_stocks_tx_cell">${gettext('Status')}</th>
                  </tr>
                </thead>
                <tbody class="smst_stocks_transactions_tbody"></tbody>
              </table>
              <div class="smst_stocks_transactions_empty" style="display:none">${gettext('No transactions yet.')}</div>
            </div>
          </div>
        </div>
      </div>
    `);

    $('#smst_stocks_loaded').append($modal);

    $modal.find('.smst_stocks_modal_tab').on('click', function () {
      const $tab = $(this);
      $tab
        .closest('.smst_stocks_modal_tabs')
        .find('.smst_stocks_modal_tab')
        .removeClass('smst_stocks_modal_tab_active');
      $tab.addClass('smst_stocks_modal_tab_active');
      const target = $tab.data('tab');
      $modal
        .find('.smst_stocks_modal_panel')
        .removeClass('smst_stocks_modal_panel_active');
      $modal
        .find(`#smst_stocks_panel_${target}`)
        .addClass('smst_stocks_modal_panel_active');
    });

    $modal
      .find('.smst_stocks_modal_close, .smst_stocks_modal_backdrop')
      .on('click', closeSmstStocksModal);

    $modal.find('.smst_stocks_modal_btn').on('click', function () {
      const action = $(this).data('action');
      if (action === 'delete') {
        deleteSmstProduct(product.id);
      } else if (action === 'buy') {
        showSuccessMessage(
          gettext('Buy Product'),
          gettext('Purchase recorded successfully')
        );
      } else if (action === 'sell') {
        showSuccessMessage(
          gettext('Sell Product'),
          gettext('Sale recorded successfully')
        );
      } else if (action === 'edit') {
        closeSmstStocksModal();
        showSuccessMessage(
          gettext('Edit Product'),
          gettext('Open the product editor to modify this item.')
        );
      }
    });

    requestAnimationFrame(() => $modal.addClass('smst_stocks_modal_open'));
    fetchSmstTransactions(product.id, $modal);
  }

  function fetchSmstTransactions(productId, $modal) {
    $.ajax({
      type: 'GET',
      url: smstTransactionApi,
      headers: {
        Authorization: `Bearer ${access}`,
      },
      success: function (response) {
        const list = Array.isArray(response)
          ? response
          : response.results || [];
        const $tbody = $modal.find('.smst_stocks_transactions_tbody');
        const $empty = $modal.find('.smst_stocks_transactions_empty');
        const txns = list.filter(
          (t) =>
            t.product == productId ||
            t.product_id == productId ||
            t.smst_stock_product == productId ||
            t.stock_product == productId
        );
        if (!txns.length) {
          $tbody.empty();
          $empty.show();
          return;
        }
        $empty.hide();
        $tbody.empty();
        txns.forEach((t) => {
          const date = escSmst(
            t.transaction_date || t.date || t.created_at || t.created || '—'
          );
          const type = escSmst(t.transaction_type || t.type || t.action || '—');
          const quantity = escSmst(t.quantity || t.qty || t.amount || '—');
          const reference = escSmst(
            t.reference || t.reference_no || t.transaction_id || '—'
          );
          const status = escSmst(t.status || 'Completed');
          $tbody.append(`
            <tr>
              <td class="smst_stocks_tx_cell">${date}</td>
              <td class="smst_stocks_tx_cell">${type}</td>
              <td class="smst_stocks_tx_cell">${quantity}</td>
              <td class="smst_stocks_tx_cell">${reference}</td>
              <td class="smst_stocks_tx_cell"><span class="smst_stocks_tx_status">${status}</span></td>
            </tr>
          `);
        });
      },
      error: function () {
        $modal.find('.smst_stocks_transactions_tbody').empty();
        $modal.find('.smst_stocks_transactions_empty').show();
      },
    });
  }

  function deleteSmstProduct(productId) {
    $.ajax({
      type: 'DELETE',
      url: `${smstProductApiBase}${productId}/`,
      headers: {
        Authorization: `Bearer ${access}`,
      },
      success: function () {
        closeSmstStocksModal();
        $(`.smst_table_row[data-product-id="${escSmst(productId)}"]`).remove();
        showSuccessMessage(
          gettext('Deleted'),
          gettext('Product deleted successfully')
        );
      },
      error: function () {
        showErrorMessage(
          gettext('Delete Failed'),
          gettext('Could not delete the product.')
        );
      },
    });
  }

  $('body').on('click', '.smst_table_row', function () {
    const productId = $(this).data('product-id');
    const product = smstProductMap[productId];
    if (product) {
      openSmstStocksModal(product);
    }
  });

  if ($('#smst_stocks_loaded').length) {
    $.ajax({
      type: 'GET',
      url: 'https://cloud.smartstock.africa/stock_products/',
      headers: {
        Authorization: `Bearer ${access}`,
      },
      success: function (response) {
        let $tableHolder = $(
          '<div id="product" class="smst_table_holder"></div>'
        );
        let $table = $(
          `<table class="smst_table">
            <thead>
              <tr>
                <th class="smst_table_head smst_table_id">#</th>
                <th class="smst_table_head smst_table_image">${gettext(
                  'Image'
                )}</th>
                <th class="smst_table_head smst_table_name">${gettext(
                  'Product Name'
                )}</th>
                <th class="smst_table_head smst_table_description">${gettext(
                  'Description'
                )}</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>`
        );
        let $tbody = $table.find('tbody');
        let $product = response.map((product) => {
          let $tableRow = $(
            `<tr class="smst_table_row animate__animated animate__fadeInUp" data-product-id="${product.id}" ></tr>`
          );
          let $productImage = $(
            `<div class="smst_product_photo"><div class="smst_product_photo_holder"><img src="${product.product_image}" alt="Product Image of Smst Product ${product.product_name}" loading="lazy"></div><div class="product_element_logo_holder">
              <svg
   width="24px"
   height="24px"
   viewBox="0 0 512 512"
   version="1.1"
   id="svg1"
   xmlns:xlink="http://www.w3.org/1999/xlink"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg">
  <defs
     id="defs1">
    <linearGradient
       id="linearGradient11">
      <stop
         style="stop-color:#8e5710;stop-opacity:1;"
         offset="0"
         id="stop11" />
      <stop
         style="stop-color:#74430a;stop-opacity:1;"
         offset="1"
         id="stop12" />
    </linearGradient>
    <linearGradient
       id="linearGradient9">
      <stop
         style="stop-color:#77490e;stop-opacity:1;"
         offset="0"
         id="stop9" />
      <stop
         style="stop-color:#a46314;stop-opacity:0;"
         offset="1"
         id="stop10" />
    </linearGradient>
    <linearGradient
       xlink:href="#linearGradient9"
       id="linearGradient10"
       x1="250.41335"
       y1="216.25046"
       x2="250.4306"
       y2="76.248596"
       gradientUnits="userSpaceOnUse" />
    <linearGradient
       xlink:href="#linearGradient11"
       id="linearGradient12"
       x1="348.78549"
       y1="148.65802"
       x2="348.78549"
       y2="218.5414"
       gradientUnits="userSpaceOnUse" />
  </defs>
  <g
     id="layer1">
    <path
       d="m 250.4306,76.248597 c -0.67602,-6.97e-4 -1.35799,0.03381 -2.02846,0.105203 -1.31765,0.14084 -2.5189,0.417262 -3.48286,0.801453 l -172.002717,68.440997 -0.0366,0.0134 V 286.89101 L 250.41326,357.5317 427.94656,286.89101 V 145.60964 l -0.0366,-0.0134 -172.00272,-68.440997 c -1.47163,-0.586109 -3.4486,-0.904564 -5.47664,-0.906656 z"
       style="display:inline;fill:#a46314;stroke-width:31.5397;stroke-linecap:square;stroke-miterlimit:2.5"
       id="path5"
       transform="matrix(1.0138943,0,0,1.0210951,2.1074218,34.926134)" />
    <path
       style="display:inline;fill:url(#linearGradient10);stroke:none;stroke-width:31.5397;stroke-linecap:square;stroke-miterlimit:2.5;stroke-opacity:1"
       id="path6"
       width="191.07158"
       height="191.07158"
       x="-157.66823"
       y="236.1053"
       ry="0"
       d="M 72.879631,145.60963 244.91928,77.154892 a 7.7697864,3.0916052 0 0 1 10.98814,0 l 172.03965,68.454738 -177.53372,70.64083 z"
       transform="matrix(1.0138943,0,0,1.0210951,2.1074218,34.926134)" />
    <path
       d="M 250.41335,216.25046 V 357.53171 L 427.94656,286.89108 V 145.58054 Z"
       style="display:inline;fill:#8e5710;fill-opacity:1;stroke:none;;stroke-linecap:square;stroke-miterlimit:2.5;stroke-opacity:1"
       id="path7"
       transform="matrix(1.0138943,0,0,1.0210951,2.1074218,34.926134)" />
    <path
       d="m 72.88015,145.58054 v 141.31054 l 177.5332,70.64063 V 216.25046 Z"
       style="display:inline;fill:#77490e;fill-opacity:1;stroke:none;;stroke-linecap:square;stroke-miterlimit:2.5"
       id="path8"
       transform="matrix(1.0138943,0,0,1.0210951,2.1074218,34.926134)" />
    <path
       id="path9"
       style="display:none;fill:#78480d;fill-opacity:1;stroke-width:5.6111;stroke-linecap:square;stroke-miterlimit:2.5"
       d="m 151.1108,156.20601 31.58432,-12.56743 177.86364,70.51032 -31.58431,12.56743 z"
       transform="matrix(1.0138943,0,0,1.0210951,-3.5568477,-5.4246026)" />
    <path
       style="fill:url(#linearGradient12);fill-opacity:1;stroke:none;stroke-width:5;stroke-linecap:square;stroke-miterlimit:2.5"
       d="m 256.01758,112.7832 -0.0175,142.95522 180.00043,-72.13101 z"
       id="path10" />
  </g>
</svg>
            </div></div>`
          );
          let descriptions = Array.isArray(product.product_description)
            ? product.product_description
            : [];
          let $descriptionList = descriptions.length
            ? $('<ul class="smst_table_description_list"></ul>').append(
                descriptions.map((description) =>
                  $('<li class="smst_table_description_item"></li>').append(
                    $('<span class="descriptionType"></span>').text(
                      description.descriptionType || ''
                    ),
                    $('<span class="descriptionValue"></span>').text(
                      description.descriptionValue || ''
                    )
                  )
                )
              )
            : $('<span class="smst_table_empty">—</span>');

          $tableRow.append(
            $(
              `<td class="smst_table_cell smst_table_id" data-label="#">${product.id}</td>`
            ),
            $(
              `<td class="smst_table_cell smst_table_image" data-label="${gettext(
                'Image'
              )}"></td>`
            ).append($productImage),
            $(
              `<td class="smst_table_cell smst_table_name" data-label="${gettext(
                'Product Name'
              )}"><span class="smst_product_name">${product.product_name}</span></td>`
            ),
            $(
              `<td class="smst_table_cell smst_table_description" data-label="${gettext(
                'Description'
              )}"></td>`
            ).append($descriptionList)
          );
          return $tableRow;
        });
        response.forEach((product) => {
          smstProductMap[product.id] = product;
        });
        $tbody.append($product);
        $tableHolder.append($table);
        $('#smst_stocks_loaded').append($tableHolder);
      },
    });
  }

  $('body').on('input', 'textarea', function () {
    this.style.height = 'auto';

    // Set the new height equal to the scroll height
    this.style.height = this.scrollHeight + 'px';
  });

  if ($('.is-active').length) {
    $('.is-active')[0].scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    });
  }
});
