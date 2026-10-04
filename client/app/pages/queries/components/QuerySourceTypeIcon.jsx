import PropTypes from "prop-types";
import React from "react";
import TypeLogo from "@/components/TypeLogo";
import { IMG_ROOT } from "@/services/data-source";

export function QuerySourceTypeIcon(props) {
  return <TypeLogo src={`${IMG_ROOT}/${props.type}.png`} label={props.type} width={20} alt={props.alt} />;
}

QuerySourceTypeIcon.propTypes = {
  type: PropTypes.string,
  alt: PropTypes.string,
};
