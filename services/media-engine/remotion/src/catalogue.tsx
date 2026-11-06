/**
 * Template catalogue. Add a template here and it becomes available to the API, the Studio and the
 * Player with no changes to the engine.
 */

import type {TemplateComponent} from "./template";
import {ChildrensStory} from "./templates/childrens-story";
import {Educational} from "./templates/educational";
import {YouTubeEditorial} from "./templates/editorial";
import {Shorts, YouTubeShorts} from "./templates/shorts";
import {Storytelling} from "./templates/storytelling";

export const CATALOGUE: Record<string, TemplateComponent> = {
  "youtube-editorial": YouTubeEditorial,
  "childrens-story": ChildrensStory,
  educational: Educational,
  storytelling: Storytelling,
  shorts: Shorts,
  "youtube-shorts": YouTubeShorts,
};

export const DEFAULT_TEMPLATE = "youtube-editorial";

export function getTemplate(id: string | undefined): TemplateComponent {
  return CATALOGUE[id ?? ""] ?? CATALOGUE[DEFAULT_TEMPLATE];
}

export function isTemplate(id: string): boolean {
  return Object.prototype.hasOwnProperty.call(CATALOGUE, id);
}

export const TEMPLATE_IDS = Object.keys(CATALOGUE);
